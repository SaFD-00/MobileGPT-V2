import json
import os
from collections import deque
from enum import Enum
import time
import xml.etree.ElementTree as ET

import pandas as pd

from agents.derive_agent import DeriveAgent  # 액션 유도/학습 에이전트
from agents.explore_agent import ExploreAgent  # 화면 탐색 에이전트
from agents.select_agent import SelectAgent  # 서브태스크 선택 에이전트
from memory.memory_manager import Memory  # 메모리 관리자 (학습된 작업 저장/불러오기)
from utils.utils import log, parse_completion_rate  # 유틸리티 함수들


class Status(Enum):
    """작업 상태를 나타내는 열거형"""
    LEARN = 0    # 학습 모드: 새로운 작업을 배우는 중
    RECALL = 1   # 재현 모드: 학습된 작업을 실행하는 중
    WAIT = 2     # 대기 모드: 다음 동작을 기다리는 중
    AUTO_EXPLORE = 3  # 자동 탐색 모드: 새로운 화면을 탐색하는 중


class MobileGPT:
    """모바일 디바이스 자동화를 위한 메인 에이전트 클래스"""
    def __init__(self, socket):
        """MobileGPT 초기화

        Args:
            socket: 클라이언트와 통신할 소켓 객체
        """
        self.socket = socket

        # XML 관련 변수들 (화면 상태 정보)
        self.encoded_xml = ""      # 인코딩된 XML (간단한 형식)
        self.hierarchy_xml = ""    # 계층 구조 XML (전체 UI 구조)
        self.parsed_xml = ""       # 파싱된 XML (처리된 형식)

        # 작업 관련 변수들
        self.instruction = ""      # 사용자가 요청한 명령어
        self.task = None           # 현재 수행 중인 작업 정보
        self.memory = None         # 메모리 관리자 인스턴스

        # 서브태스크 관련 변수들
        self.current_subtask = None         # 현재 진행 중인 서브태스크
        self.current_screen_xml = ""        # 현재 화면의 XML
        self.current_page_index = -1        # 현재 페이지 인덱스
        self.current_subtask_data = {}      # 현재 서브태스크 데이터

        # 히스토리 추적 변수들
        self.subtask_history = []    # 수행한 서브태스크 히스토리
        self.task_path = []          # 전체 작업 경로 (학습용)
        self.qa_history = []         # Q&A 히스토리 (사용자 입력)

        # 에이전트 인스턴스들
        self.explore_agent = None    # 화면 탐색 에이전트
        self.select_agent = None     # 서브태스크 선택 에이전트
        self.derive_agent = None     # 액션 유도 에이전트

        # 작업 및 서브태스크 상태 플래그
        self.task_status = Status.RECALL      # 기본적으로 재현 모드로 시작
        self.subtask_status = Status.WAIT     # 기본적으로 대기 상태로 시작

        # 탐색 모드 관련 변수들 (EXPLORE 모드에서 사용)
        self.explored_subtasks = {}  # State별 시도한 서브태스크 추적 {(page_index, state_index): [(subtask_name, trigger_ui_index), ...]}
        self.explored_uis = {}       # State별 시도한 UI 인덱스 추적 {(page_index, state_index): [ui_indexes]}

        # 마지막 탐색 액션 추적 변수 (화면 전환 후 explored로 마킹하고 actions.csv에 저장하기 위함)
        self.last_explored_page_index = None  # 마지막으로 클릭한 페이지 인덱스
        self.last_explored_state_index = None  # 마지막으로 클릭한 state 인덱스 [NEW]
        self.last_explored_ui_index = None    # 마지막으로 클릭한 UI 인덱스
        self.last_explored_action = None      # 마지막으로 수행한 액션
        self.last_explored_screen = None      # 마지막 화면 XML (액션 일반화용)

        # [NEW] State 추적 변수
        self.current_state_index = -1
        self.prev_state_index = -1
        self.state_history = []  # [(page, state), ...]

    def init(self, instruction: str, task: dict, is_new_task: bool):
        """에이전트 초기화 및 작업 설정

        Args:
            instruction: 사용자가 요청한 명령어
            task: 작업 정보 딕셔너리 (app, name 등 포함)
            is_new_task: 새로운 작업인지 여부 (True면 학습 모드)
        """
        self.instruction = instruction
        self.task = task

        # 메모리 관리자 초기화 (앱별로 작업 정보 저장/로드)
        self.memory = Memory(task['app'], instruction, task['name'])

        # 각 에이전트 초기화
        self.explore_agent = ExploreAgent(self.memory)  # 새로운 화면 탐색
        self.select_agent = SelectAgent(self.memory, self.instruction)  # 서브태스크 선택
        self.derive_agent = DeriveAgent(self.memory, self.instruction)  # 액션 생성/학습

        # 시간 측정용 변수
        self.start_time = time.time()
        self.end_time = 0

        # 새로운 작업이면 학습 모드로 설정
        if is_new_task:
            self.task_status = Status.LEARN

        log('Mobile Agent Initialized for app: ' + task['app'] + ' / Task: ' + task['name'])

    def _handle_state_transition(self, page_index: int, new_state_index: int):
        """State 전환 처리

        Args:
            page_index: 현재 페이지 인덱스
            new_state_index: 새로운 state 인덱스
        """
        self.prev_state_index = self.current_state_index
        self.current_state_index = new_state_index
        self.state_history.append((page_index, new_state_index))

        log(f"State transition: page={page_index}, "
            f"state {self.prev_state_index} -> {new_state_index}", "blue")

    def get_next_action(self, parsed_xml=None, hierarchy_xml=None, encoded_xml=None):
        """현재 화면 상태를 분석하고 다음 동작을 결정

        Args:
            parsed_xml: 파싱된 XML 문자열
            hierarchy_xml: 계층 구조 XML 문자열
            encoded_xml: 인코딩된 XML 문자열

        Returns:
            dict: 다음 수행할 액션 정보
        """
        log(":::::::::MobileGPT received new screen:::::::::", 'red')

        # XML 데이터 업데이트 (기존 값이 없으면 저장된 값 사용)
        parsed_xml = parsed_xml or self.parsed_xml
        hierarchy_xml = hierarchy_xml or self.hierarchy_xml
        encoded_xml = encoded_xml or self.encoded_xml

        self.parsed_xml = parsed_xml
        self.hierarchy_xml = hierarchy_xml
        self.encoded_xml = encoded_xml

        self.current_screen_xml = encoded_xml

        # [MODIFIED] 메모리에서 page + state 검색
        page_index, state_index, similarity = self.memory.search_node(
            parsed_xml, hierarchy_xml, encoded_xml
        )

        # 새로운 화면이면 탐색
        if page_index == -1:
            page_index = self.explore_agent.explore(parsed_xml, hierarchy_xml, encoded_xml)
            # 새 페이지는 state 0으로 시작
            state_index = 0

        # State 변화 추적
        if state_index != self.current_state_index:
            self._handle_state_transition(page_index, state_index)

        # 페이지 관리자 초기화 (state 포함)
        if page_index != self.current_page_index or state_index != self.current_state_index:
            self.memory.init_page_manager(page_index, state_index)
            self.current_page_index = page_index
            self.current_state_index = state_index
            # 참고: 페이지 전환은 subtask의 정상적인 일부일 수 있음 (예: 검색창 클릭 → 키보드 화면)
            # subtask 종료는 DeriveAgent가 finish 액션을 반환했을 때만 수행 (라인 236-238)

        # 현재 페이지에서 수행 가능한 서브태스크들 가져오기
        available_subtasks = self.memory.get_available_subtasks(page_index)

        # 현재 서브태스크가 없으면 새로운 서브태스크 선택
        if self.current_subtask is None:
            # 메모리에서 다음 서브태스크 가져오기 (재현 모드)
            next_subtask = self.memory.get_next_subtask(page_index, self.qa_history, self.current_screen_xml)

            # 메모리에 없으면 선택 에이전트로 새로운 서브태스크 선택 (학습 모드)
            if not next_subtask:
                response, new_action = self.select_agent.select(available_subtasks, self.subtask_history,
                                                                self.qa_history,
                                                                encoded_xml)

                # 새로운 액션이 생성되면 메모리에 추가
                if new_action:
                    self.memory.add_new_action(new_action, page_index)
                    available_subtasks = self.memory.get_available_subtasks(page_index)

                next_subtask = response['action']
                # read_screen이 아닌 경우 사용자에게 음성 메시지 전송
                if next_subtask['name'] != 'read_screen':
                    msg = response['speak']
                    self.__send_speak_action(msg)

            # 이전 서브태스크 데이터를 작업 경로에 추가
            if self.current_subtask_data:
                self.task_path.append(self.current_subtask_data)

            # 새로운 서브태스크 데이터 초기화 (state 포함)
            self.current_subtask_data = {
                "page_index": self.current_page_index,
                "state_index": self.current_state_index,  # [NEW]
                "subtask_name": next_subtask['name'],
                "subtask": next_subtask,
                "actions": []
            }

            # 유도 에이전트에 새로운 서브태스크 설정
            self.derive_agent.init_subtask(next_subtask, self.subtask_history)
            self.current_subtask = next_subtask

            # 기본 서브태스크는 즉시 처리 (finish, speak, scroll_screen)
            if next_subtask['name'] in ['finish', 'speak', 'scroll_screen']:
                return self.__handle_primitive_subtask(next_subtask)

        # 서브태스크 파라미터 처리 (주석 처리된 코드: 미지의 파라미터 처리용)
        subtask_parameters = self.current_subtask['parameters']
        # for key, value in subtask_parameters.items():
        #     if value == "unknown":  # 파라미터 값이 알려지지 않은 경우
        #         raw_subtask = next(
        #             (subtask for subtask in available_subtasks if subtask['name'] == self.current_subtask['name']),
        #             None)
        #         print(raw_subtask)
        #         if raw_subtask:
        #             if isinstance(raw_subtask['parameters'], str):
        #                 raw_subtask['parameters'] = json.loads(raw_subtask['parameters'])
        #             question = raw_subtask['parameters'][key]
        #             # 사용자에게 질문하는 액션 생성
        #             ask_action = {"name": "ask", "parameters": {"info_name": key, "question": question}}
        #             return ask_action

        # 메모리에서 다음 액션 가져오기 (재현 모드)
        next_action = self.memory.get_next_action(self.current_subtask, self.encoded_xml)

        # [MODIFIED] 액션 데이터에 state 정보 포함
        current_action_data = {
            "page_index": self.current_page_index,
            "state_index": self.current_state_index,  # [NEW]
            "action": next_action,
            "screen": self.encoded_xml,
            "example": {}
        }

        # 메모리에 액션이 있는 경우 (재현 모드)
        if next_action:
            self.subtask_status = Status.RECALL
            # 예제가 있으면 유도 에이전트로 구체적인 액션 생성
            if "examples" in next_action:
                next_action, example = self.derive_agent.derive(self.encoded_xml, examples=next_action['examples'])
                current_action_data['action'] = next_action
                current_action_data['example'] = example

        # 메모리에 액션이 없는 경우
        else:
            # 대기 또는 학습 상태면 새로운 액션 학습
            if self.subtask_status == Status.WAIT or self.subtask_status == Status.LEARN:
                self.subtask_status = Status.LEARN
                # 유도 에이전트로 새로운 액션 생성 (학습)
                next_action, example = self.derive_agent.derive(self.encoded_xml)
                current_action_data['action'] = next_action
                current_action_data['example'] = example

            # 재현 모드에서 액션이 없으면 분기 처리
            elif self.subtask_status == Status.RECALL:
                self.__prepare_diverge_subtask()  # 서브태스크 분기 준비
                return self.get_next_action(parsed_xml, hierarchy_xml, encoded_xml)  # 재귀 호출

        # 현재 서브태스크의 액션 리스트에 추가
        self.current_subtask_data['actions'].append(current_action_data)

        # finish 액션이면 서브태스크 종료하고 다음 액션 가져오기
        if next_action['name'] == 'finish':
            self.__finish_subtask(mark_finish=False, explicit_finish=True)
            next_action = self.get_next_action(parsed_xml, hierarchy_xml, encoded_xml)

        return next_action

    def set_qa_answer(self, info_name: str, question: str, answer: str):
        """사용자로부터 Q&A 응답을 받아 처리

        Args:
            info_name: 정보 이름 (파라미터 키)
            question: 사용자에게 한 질문
            answer: 사용자의 답변

        Returns:
            dict: 다음 수행할 액션 (get_next_action 호출 결과)
        """
        # Q&A 히스토리에 추가
        qa = {"info": info_name, "question": question, "answer": answer}
        self.qa_history.append(qa)

        # 현재 서브태스크의 파라미터에 답변 설정
        subtask_parameters = self.current_subtask['parameters']
        if info_name in subtask_parameters:
            subtask_parameters[info_name] = answer  # 파라미터 값 업데이트
            return self.get_next_action()  # 다음 액션 진행
        else:
            log(f"Something wrong. Cannot find {info_name} inside subtask: {self.current_subtask}", "red")

    def __finish_subtask(self, mark_finish=True, explicit_finish=False):
        """현재 서브태스크를 완료 처리

        Args:
            mark_finish: finish 액션을 추가할지 여부
            explicit_finish: 명시적 finish 액션인지 여부
        """
        log("finish subtask!!", "red")
        log(f"subtask: {self.subtask_status}, task: {self.task_status}", "red")

        # 학습 모드에서 서브태스크 완료 시
        if self.subtask_status == Status.LEARN and self.task_status == Status.LEARN:
            # finish 액션 마킹이 필요한 경우
            if mark_finish:
                finish_action = {"name": "finish", "parameters": {}}
                self.current_subtask_data['actions'].append(
                    {
                        "page_index": self.current_page_index,
                        "state_index": self.current_state_index,  # [NEW]
                        "action": finish_action,
                        "screen": self.encoded_xml,
                        "example": {}
                    }
                )

            # guideline 생성 (summarize_actions 전에 호출해야 함 - response_history가 초기화되기 전)
            guideline = ""
            if self.derive_agent:
                guideline = self.derive_agent.generate_guideline()

            # 서브태스크를 guideline과 함께 저장
            if self.current_subtask and self.memory:
                example = {"instruction": self.instruction, "screen": self.encoded_xml}
                self.memory.save_subtask(self.current_subtask, example, guideline)

            action_summary = None
            if self.derive_agent:
                action_summary = self.derive_agent.summarize_actions()
            if action_summary:
                self.subtask_history.append(action_summary)

        if self.subtask_status == Status.RECALL:
            if explicit_finish:
                history = f"Performed an action: {self.current_subtask}"
                self.subtask_history.append(history)

        self.current_subtask = None
        self.subtask_status = Status.WAIT

    def __prepare_diverge_subtask(self) -> None:
        """
        새로운 서브태스크로 분기하기 위한 준비 작업
        Returns:
        """
        history = f"I have performed an action: {self.current_subtask}. But I am not sure if it was successful."
        self.subtask_history.append(history)

        self.current_subtask = None
        self.subtask_status = Status.WAIT

    def __send_speak_action(self, msg) -> None:
        """
        디바이스에 음성 출력 액션 전송
        Args:
            msg: 디바이스에서 출력할 메시지
        """
        speak_action = {"name": "speak", "parameters": {"message": msg}}  # speak action
        self.socket.send(json.dumps(speak_action).encode())
        self.socket.send("\r\n".encode())

    def __handle_primitive_subtask(self, next_subtask: dict) -> None:
        """기본 서브태스크(finish, speak, scroll) 처리"""
        if next_subtask['name'] == 'finish':
            self.__finish_task()
            return

        elif next_subtask['name'] == 'speak':
            msg = next_subtask['parameters']['message']
            speak_action = {"name": "speak", "parameters": {"message": msg}}  # speak action
            self.socket.send(json.dumps(speak_action).encode())
            self.socket.send("\r\n".encode())

            history = f"Spoke to the user: '{msg}'"
            self.subtask_history.append(history)
            self.current_subtask = None
            self.subtask_status = Status.WAIT

            completion_rate = parse_completion_rate(next_subtask['parameters']['completion_rate'])
            return self.get_next_action()

        elif next_subtask['name'] == 'scroll_screen':
            direction = next_subtask['parameters']['direction']
            index = next_subtask['parameters']['scroll_ui_index']

            scroll_action = {"name": "scroll", "parameters": {"index": index, "direction": direction}}
            self.socket.send(json.dumps(scroll_action).encode())
            self.socket.send("\r\n".encode())

            if self.task_status == Status.LEARN:
                target_info = next_subtask['parameters']['target_info']
                history = f"Scrolled screen {direction} to find '{target_info}'"
                self.subtask_history.append(history)
            self.current_subtask = None
            self.subtask_status = Status.WAIT

    def __finish_task(self) -> None:
        """
        전체 작업을 완료하고 결과를 저장
        Returns:
        """
        log("------------END OF THE TASK------------", "blue")

        self.end_time = time.time()
        elapsed_time = self.end_time - self.start_time
        minutes = int(elapsed_time / 60)
        seconds = int(elapsed_time)

        log(f"""Completed the execution of "{self.instruction}" you commanded, and the Task took a total of [{minutes} minutes({seconds} seconds)] to run.""", "green")

        self.current_subtask = None
        self.subtask_status = Status.WAIT

        self.socket.send("$$$$$".encode())
        self.socket.send("\r\n".encode())

        self.subtask_history = [f'Performed an instruction {self.instruction}']

        self.task_path.append({"page_index": self.current_page_index,
                               "state_index": self.current_state_index,  # [NEW]
                               "subtask_name": "finish",
                               "subtask": {"name": "finish",
                                           "description": "Use this to signal that the task has been completed",
                                           "parameters": {}
                                           },
                               "actions": []})
        if self.task_status == Status.LEARN:
            # 학습된 작업 경로를 메모리에 저장
            # self.task_path = self.memory.merge_subtasks(self.task_path)

            global_task_database_path = f"./memory/tasks.csv"
            global_task_database = pd.read_csv(global_task_database_path)
            global_task_database = pd.concat([global_task_database, pd.DataFrame([self.task])], ignore_index=True)
            global_task_database.to_csv(global_task_database_path, index=False)

            self.memory.save_task(self.task_path)
        # self.memory.save_task_path(self.task_path)

    # ==================== 탐색 모드 (EXPLORE) 메서드들 ====================

    def init_explore(self, app_name: str, algorithm: str = "DFS"):
        """탐색 모드 초기화

        Args:
            app_name: 탐색할 앱 이름
            algorithm: 탐색 알고리즘 ("DFS", "BFS", "GREEDY_BFS", "GREEDY_DFS")
        """
        self.task_status = Status.AUTO_EXPLORE
        self.memory = Memory(app_name, "hardcode", "hardcode")
        self.explore_agent = ExploreAgent(self.memory)
        self.derive_agent = DeriveAgent(self.memory, "exploration")  # Multi-step 탐색용

        # 기존 변수
        self.explored_subtasks = {}
        self.explored_uis = {}

        # 새로운 탐색 변수
        self.exploration_algorithm = algorithm       # "DFS", "BFS", "GREEDY"
        self.visited_pages = set()                   # 방문한 (page, state) 튜플 집합
        self.exploration_stack = []                  # DFS용 스택 [(page_index, state_index, subtask_info), ...]
        self.exploration_queue = []                  # BFS용 큐 [(page_index, state_index, subtask_info), ...]
        self.page_graph = {}                         # 페이지 간 연결 그래프 {from: [(to, subtask_name), ...]}
        self.back_edges = {}                         # Back 액션으로 이동한 역방향 edge {from: [to, ...]}
        self.traversal_path = []                     # 현재 탐색 경로 (back 복귀용)
        self.navigation_plan = []                    # 네비게이션 계획 [(page, subtask), ...]
        self.start_page_index = None                 # 시작 페이지 인덱스
        self.start_state_index = None                # 시작 state 인덱스
        self.unexplored_subtasks = {}                # Greedy용: {(page_index, state_index): [subtask_info, ...]}

        # Multi-step 탐색 관련 변수
        self.current_exploring_subtask = None        # 현재 탐색 중인 서브태스크 정보
        self.current_exploration_actions = []        # 현재 서브태스크의 액션 히스토리
        self.current_exploration_step = 0            # 현재 스텝 번호
        self.max_exploration_steps = 10              # 최대 스텝 수

        # 기존 메모리에서 데이터 로드
        self._build_page_graph_from_memory()
        self._load_unexplored_subtasks()

        log(f"Explore mode initialized for app: {app_name} with {algorithm} algorithm", "blue")

    def get_explore_action(self, parsed_xml, hierarchy_xml, encoded_xml, page_index, state_index=0):
        """DFS/BFS/Greedy 알고리즘에 따라 다음 탐색 액션 반환

        Args:
            parsed_xml: 파싱된 XML 화면 구조
            hierarchy_xml: 계층 구조 XML
            encoded_xml: 인코딩된 XML
            page_index: 현재 페이지 인덱스
            state_index: 현재 state 인덱스 (기본값 0)

        Returns:
            dict: 다음 액션 또는 None
        """
        # 시작 페이지/state 기록
        if self.start_page_index is None:
            self.start_page_index = page_index
            self.start_state_index = state_index

        page_state_key = (page_index, state_index)

        # 새로운 (page, state) 방문 시 초기화
        if page_state_key not in self.visited_pages:
            self._register_new_page(page_index, state_index, encoded_xml)

        # 알고리즘에 따라 다음 액션 결정
        if self.exploration_algorithm == "DFS":
            return self._get_dfs_action(parsed_xml, encoded_xml, page_index, state_index)
        elif self.exploration_algorithm == "BFS":
            return self._get_bfs_action(parsed_xml, encoded_xml, page_index, state_index)
        elif self.exploration_algorithm == "GREEDY_BFS":
            return self._get_greedy_bfs_action(parsed_xml, encoded_xml, page_index, state_index)
        elif self.exploration_algorithm == "GREEDY_DFS":
            return self._get_greedy_dfs_action(parsed_xml, encoded_xml, page_index, state_index)
        else:
            log(f"Unknown exploration algorithm: {self.exploration_algorithm}", "red")
            return None

    def _build_page_graph_from_memory(self):
        """기존 subtasks.csv 데이터로 페이지 그래프 구축"""
        pages_dir = self.memory.page_database_path
        if not os.path.exists(pages_dir):
            return

        for page_folder in os.listdir(pages_dir):
            page_path = os.path.join(pages_dir, page_folder)
            subtasks_file = os.path.join(page_path, "subtasks.csv")

            if os.path.exists(subtasks_file):
                try:
                    subtasks_df = pd.read_csv(subtasks_file)
                    for _, row in subtasks_df.iterrows():
                        start_page = int(row['start'])
                        end_page = int(row['end'])
                        subtask_name = row['name']

                        if start_page not in self.page_graph:
                            self.page_graph[start_page] = []

                        self.page_graph[start_page].append((end_page, subtask_name))
                except Exception as e:
                    log(f"Error reading subtasks.csv for page {page_folder}: {e}", "yellow")

        log(f"Page graph built: {self.page_graph}", "blue")

    def _load_unexplored_subtasks(self):
        """available_subtasks.csv에서 state별 unexplored 서브태스크 로드 (모든 trigger UI별로)"""
        pages_dir = self.memory.page_database_path
        if not os.path.exists(pages_dir):
            return

        for page_folder in os.listdir(pages_dir):
            try:
                page_index = int(page_folder)
            except ValueError:
                continue

            page_path = os.path.join(pages_dir, page_folder)

            # states.csv에서 state 목록 가져오기
            states_csv = os.path.join(page_path, "states.csv")
            state_indices = []

            if os.path.exists(states_csv):
                try:
                    states_df = pd.read_csv(states_csv)
                    state_indices = states_df['state_index'].tolist()
                except Exception as e:
                    log(f"Error reading states.csv for page {page_folder}: {e}", "yellow")
                    continue
            else:
                # states.csv가 없으면 state 0만 존재한다고 가정 (마이그레이션 전 데이터)
                state_indices = [0]

            # 각 state별로 unexplored subtasks 로드
            for state_index in state_indices:
                state_path = os.path.join(page_path, str(state_index))
                available_file = os.path.join(state_path, "available_subtasks.csv")

                if os.path.exists(available_file):
                    try:
                        available_df = pd.read_csv(available_file)
                        unexplored_df = available_df[available_df['exploration'] == 'unexplored']

                        if not unexplored_df.empty:
                            # pages.csv에서 trigger_uis 가져오기
                            page_data = self.memory.page_db.loc[self.memory.page_db['index'] == page_index]
                            if page_data.empty:
                                continue

                            trigger_uis = json.loads(page_data.iloc[0]['trigger_uis'])
                            subtask_infos = []

                            for _, row in unexplored_df.iterrows():
                                subtask_name = row['name']
                                if subtask_name in trigger_uis and trigger_uis[subtask_name]:
                                    params = row.get('parameters', {})
                                    if isinstance(params, str):
                                        try:
                                            params = json.loads(params)
                                        except (json.JSONDecodeError, TypeError):
                                            params = {}

                                    # 모든 trigger UI에 대해 별도의 subtask_info 생성
                                    for ui_info in trigger_uis[subtask_name]:
                                        subtask_info = {
                                            'name': subtask_name,
                                            'description': row.get('description', ''),
                                            'parameters': params,
                                            'trigger_ui_index': ui_info.get('index', -1),
                                            'trigger_ui_info': ui_info
                                        }
                                        subtask_infos.append(subtask_info)

                            if subtask_infos:
                                # (page, state) 튜플로 키 생성
                                self.unexplored_subtasks[(page_index, state_index)] = subtask_infos
                    except Exception as e:
                        log(f"Error reading available_subtasks.csv for page {page_folder}, state {state_index}: {e}", "yellow")

        total_items = sum(len(v) for v in self.unexplored_subtasks.values())
        log(f"Unexplored subtask-trigger combinations loaded: {total_items} items across {len(self.unexplored_subtasks)} (page, state) pairs", "blue")

    def _find_path_to_page(self, from_page: int, to_page: int) -> list:
        """BFS로 from_page에서 to_page까지의 최단 경로 탐색 (forward + back edge 사용)

        Returns:
            list: [(page, action_type, subtask_name), ...] 형태의 경로
                - action_type: "forward" 또는 "back"
                - subtask_name: forward면 subtask명, back이면 None
                - 없으면 빈 리스트
        """
        if from_page == to_page:
            return []

        queue = deque([(from_page, [])])
        visited = {from_page}

        while queue:
            current_page, path = queue.popleft()

            # Forward edges (subtask 실행으로 이동)
            if current_page in self.page_graph:
                for next_page, subtask_name in self.page_graph[current_page]:
                    if next_page in visited:
                        continue

                    new_path = path + [(current_page, "forward", subtask_name)]

                    if next_page == to_page:
                        return new_path

                    visited.add(next_page)
                    queue.append((next_page, new_path))

            # Back edges (back 액션으로 이동)
            # Page 0 제약: page 0에서는 back 불가 (앱 종료됨)
            # → current_page == 0이면 back edge 탐색하지 않음
            if current_page != 0 and current_page in self.back_edges:
                for next_page in self.back_edges[current_page]:
                    if next_page in visited:
                        continue

                    new_path = path + [(current_page, "back", None)]

                    if next_page == to_page:
                        return new_path

                    visited.add(next_page)
                    queue.append((next_page, new_path))

        return []

    def _find_nearest_unexplored(self, current_page: int) -> tuple:
        """현재 페이지에서 가장 가까운 unexplored 서브태스크 찾기

        Returns:
            tuple: (page_index, subtask_name, path) 또는 (None, None, None)
        """
        # 현재 페이지에 unexplored가 있으면 바로 반환
        if current_page in self.unexplored_subtasks and self.unexplored_subtasks[current_page]:
            subtask_name = self.unexplored_subtasks[current_page][0]
            return (current_page, subtask_name, [])

        # BFS로 가장 가까운 unexplored 페이지 찾기
        queue = deque([(current_page, [])])
        visited = {current_page}

        while queue:
            page, path = queue.popleft()

            if page not in self.page_graph:
                continue

            for next_page, subtask_name in self.page_graph[page]:
                if next_page in visited:
                    continue

                new_path = path + [(page, subtask_name)]

                # unexplored 서브태스크가 있는 페이지 발견
                if next_page in self.unexplored_subtasks and self.unexplored_subtasks[next_page]:
                    target_subtask = self.unexplored_subtasks[next_page][0]
                    return (next_page, target_subtask, new_path)

                visited.add(next_page)
                queue.append((next_page, new_path))

        return (None, None, None)

    def _register_new_page(self, page_index, state_index, encoded_xml):
        """새 (page, state) 방문 시 unexplored 서브태스크를 스택/큐에 추가 (서브태스크 기반)"""
        page_state_key = (page_index, state_index)
        self.visited_pages.add(page_state_key)
        self.explored_uis[page_state_key] = []

        # State별 available_subtasks.csv에서 unexplored 서브태스크 가져오기
        page_path = os.path.join(self.memory.page_database_path, str(page_index))
        state_path = os.path.join(page_path, str(state_index))
        available_file = os.path.join(state_path, "available_subtasks.csv")

        unexplored_subtasks = []
        if os.path.exists(available_file):
            try:
                available_df = pd.read_csv(available_file)
                unexplored_df = available_df[available_df['exploration'] == 'unexplored']
                unexplored_subtasks = unexplored_df.to_dict('records')
            except Exception as e:
                log(f"Error reading available_subtasks.csv: {e}", "yellow")

        log(f"Page {page_index} State {state_index}: found {len(unexplored_subtasks)} unexplored subtasks", "cyan")

        # unexplored 서브태스크가 없으면 리턴
        if not unexplored_subtasks:
            return

        # pages.csv에서 trigger_uis 가져오기
        page_data = self.memory.page_db.loc[self.memory.page_db['index'] == page_index]
        if page_data.empty:
            return

        trigger_uis = json.loads(page_data.iloc[0]['trigger_uis'])

        # 서브태스크 정보와 함께 스택/큐에 추가
        # 각 서브태스크의 모든 trigger UI를 별도로 추가
        subtask_infos = []
        for subtask in unexplored_subtasks:
            subtask_name = subtask['name']
            if subtask_name in trigger_uis and trigger_uis[subtask_name]:
                # 파라미터 파싱
                params = subtask.get('parameters', {})
                if isinstance(params, str):
                    try:
                        params = json.loads(params)
                    except (json.JSONDecodeError, TypeError):
                        params = {}

                # 모든 trigger UI에 대해 별도의 subtask_info 생성
                for ui_info in trigger_uis[subtask_name]:
                    subtask_info = {
                        'name': subtask_name,
                        'description': subtask.get('description', ''),
                        'parameters': params,
                        'trigger_ui_index': ui_info.get('index', -1),
                        'trigger_ui_info': ui_info
                    }
                    subtask_infos.append(subtask_info)

        log(f"Page {page_index} State {state_index}: {len(subtask_infos)} subtask-trigger combinations: {[(s['name'], s['trigger_ui_index']) for s in subtask_infos]}", "cyan")

        # 알고리즘에 따라 스택/큐에 추가 (state 포함)
        if self.exploration_algorithm == "DFS":
            for subtask_info in reversed(subtask_infos):
                self.exploration_stack.append((page_index, state_index, subtask_info))
        elif self.exploration_algorithm == "BFS":
            for subtask_info in subtask_infos:
                self.exploration_queue.append((page_index, state_index, subtask_info))
        elif self.exploration_algorithm in ["GREEDY_BFS", "GREEDY_DFS"]:
            # GREEDY_BFS/GREEDY_DFS: unexplored_subtasks 딕셔너리에 서브태스크 정보 추가
            if subtask_infos:
                self.unexplored_subtasks[page_state_key] = subtask_infos
                log(f"Page {page_index} State {state_index}: added to unexplored_subtasks", "cyan")

    def _get_dfs_action(self, parsed_xml, encoded_xml, current_page_index, current_state_index):
        """DFS: 스택 기반 깊이 우선 탐색 (Multi-step 서브태스크 지원)"""

        # 현재 진행 중인 Multi-step 서브태스크가 있으면 계속 진행
        if self.current_exploring_subtask is not None:
            return self._continue_subtask_exploration(parsed_xml, encoded_xml, current_page_index, current_state_index)

        while self.exploration_stack:
            page_index, state_index, subtask_info = self.exploration_stack[-1]

            # 다른 페이지나 state면 back으로 복귀
            if page_index != current_page_index or state_index != current_state_index:
                # 0 페이지에서는 back 불가 (앱 종료됨) - 해당 항목 스킵
                if current_page_index == 0:
                    log(f"DFS: Cannot go back from page 0, skipping subtask on page {page_index} state {state_index}", "yellow")
                    self.exploration_stack.pop()
                    continue
                if self.traversal_path and self.traversal_path[-1] == current_page_index:
                    self.traversal_path.pop()
                log(f"DFS: Need to go back from page {current_page_index} state {current_state_index} to reach page {page_index} state {state_index}", "yellow")
                return {"name": "back", "parameters": {}}

            self.exploration_stack.pop()

            # 이미 탐색한 (subtask_name, trigger_ui_index) 조합 스킵
            subtask_name = subtask_info['name']
            trigger_ui_index = subtask_info.get('trigger_ui_index', -1)
            page_state_key = (page_index, state_index)
            if (subtask_name, trigger_ui_index) in self.explored_subtasks.get(page_state_key, []):
                continue

            # 새 서브태스크 탐색 시작
            log(f"DFS: Starting multi-step exploration of subtask '{subtask_name}' (trigger_ui={trigger_ui_index}) on page {current_page_index} state {current_state_index}", "cyan")
            return self._start_subtask_exploration(parsed_xml, encoded_xml, current_page_index, current_state_index, subtask_info)

        # 스택 비었지만 시작점이 아니면 back
        if self.traversal_path:
            # 0 페이지에서는 back 불가 (앱 종료됨) - 탐색 완료로 처리
            if current_page_index == 0:
                log(f"DFS: Stack empty at page 0, exploration complete", "green")
                return None
            self.traversal_path.pop()
            log(f"DFS: Stack empty, going back from page {current_page_index}", "yellow")
            return {"name": "back", "parameters": {}}

        log("DFS: Exploration complete", "green")
        return None  # 탐색 완료

    def _start_subtask_exploration(self, parsed_xml, encoded_xml, current_page_index, current_state_index, subtask_info):
        """새 서브태스크의 Multi-step 탐색 시작"""
        subtask_name = subtask_info['name']
        trigger_ui_index = subtask_info.get('trigger_ui_index', -1)
        page_state_key = (current_page_index, current_state_index)

        # 탐색 상태 초기화
        self.current_exploring_subtask = subtask_info
        self.current_exploration_actions = []
        self.current_exploration_step = 0
        self.current_exploration_start_page = current_page_index
        self.current_exploration_start_state = current_state_index  # state 추적
        self.current_exploration_trigger_ui = trigger_ui_index  # trigger UI 추적

        # explored_subtasks에 (subtask_name, trigger_ui_index) 튜플로 기록 (키는 (page, state))
        if page_state_key not in self.explored_subtasks:
            self.explored_subtasks[page_state_key] = []
        self.explored_subtasks[page_state_key].append((subtask_name, trigger_ui_index))

        # explored_uis에도 기록 (키는 (page, state))
        if trigger_ui_index is not None and trigger_ui_index != -1:
            if page_state_key not in self.explored_uis:
                self.explored_uis[page_state_key] = []
            self.explored_uis[page_state_key].append(trigger_ui_index)

        # 첫 번째 액션: trigger UI 클릭
        action = self._create_click_action(parsed_xml, encoded_xml, trigger_ui_index, current_page_index, current_state_index)
        if action:
            self.traversal_path.append(current_page_index)
            self.current_exploration_actions.append({
                'step': 0,
                'action': action,
                'screen': encoded_xml,
                'start_page': current_page_index,
                'start_state': current_state_index
            })
            self.current_exploration_step = 1
            log(f"Multi-step: Step 0 - Clicking trigger UI {trigger_ui_index} for '{subtask_name}'", "cyan")
            return action

        # trigger UI 클릭 실패 시 서브태스크 종료
        log(f"Multi-step: Failed to click trigger UI for '{subtask_name}'", "yellow")
        self._finish_subtask_exploration(current_page_index, current_state_index, success=False)
        return None

    def _continue_subtask_exploration(self, parsed_xml, encoded_xml, current_page_index, current_state_index):
        """진행 중인 Multi-step 서브태스크 계속 탐색"""
        subtask_info = self.current_exploring_subtask
        subtask_name = subtask_info['name']

        # 이전 액션의 end_page, end_state 업데이트
        if self.current_exploration_actions:
            last_action = self.current_exploration_actions[-1]
            if 'end_page' not in last_action:
                last_action['end_page'] = current_page_index
                last_action['end_state'] = current_state_index

        # 최대 스텝 수 초과 시 종료
        if self.current_exploration_step >= self.max_exploration_steps:
            log(f"Multi-step: Max steps reached for '{subtask_name}', finishing", "yellow")
            self._finish_subtask_exploration(current_page_index, current_state_index, success=True)
            # 0 페이지에서는 back 불가 (앱 종료됨) - 다음 subtask로 이동
            if current_page_index == 0:
                log(f"Multi-step: At page 0, proceeding to next subtask", "cyan")
                return self.get_explore_action(parsed_xml, self.hierarchy_xml, encoded_xml, current_page_index, current_state_index)
            return {"name": "back", "parameters": {}}

        # DeriveAgent로 다음 액션 도출
        response = self.derive_agent.derive_exploration(
            subtask=subtask_info,
            screen=encoded_xml,
            action_history=self.current_exploration_actions,
            step=self.current_exploration_step,
            max_steps=self.max_exploration_steps
        )

        action = response.get('action', {})
        is_complete = response.get('is_subtask_complete', False)

        # 액션 기록 (state 정보 포함)
        self.current_exploration_actions.append({
            'step': self.current_exploration_step,
            'action': action,
            'screen': encoded_xml,
            'reasoning': response.get('reasoning', ''),
            'start_page': current_page_index,
            'start_state': current_state_index
            # end_page, end_state는 다음 화면에서 업데이트
        })
        self.current_exploration_step += 1

        # finish 액션이거나 서브태스크 완료 시
        if action.get('name') == 'finish' or is_complete:
            log(f"Multi-step: Subtask '{subtask_name}' completed after {self.current_exploration_step} steps", "green")
            self._finish_subtask_exploration(current_page_index, current_state_index, success=True)
            # 0 페이지에서는 back 불가 (앱 종료됨) - 다음 subtask로 이동
            if current_page_index == 0:
                log(f"Multi-step: At page 0, proceeding to next subtask", "cyan")
                return self.get_explore_action(parsed_xml, self.hierarchy_xml, encoded_xml, current_page_index, current_state_index)
            return {"name": "back", "parameters": {}}

        log(f"Multi-step: Step {self.current_exploration_step - 1} - {action.get('name')} for '{subtask_name}'", "cyan")
        return action

    def _finish_subtask_exploration(self, end_page_index, end_state_index, success=True):
        """Multi-step 서브태스크 탐색 완료 및 저장"""
        if self.current_exploring_subtask is None:
            return

        subtask_info = self.current_exploring_subtask
        subtask_name = subtask_info['name']
        trigger_ui_index = getattr(self, 'current_exploration_trigger_ui', -1)
        start_page = self.current_exploration_start_page
        start_state = getattr(self, 'current_exploration_start_state', 0)
        actions = self.current_exploration_actions

        # 마지막 액션의 end_page, end_state 업데이트
        if actions and 'end_page' not in actions[-1]:
            actions[-1]['end_page'] = end_page_index
            actions[-1]['end_state'] = end_state_index

        log(f"Finishing subtask '{subtask_name}' (trigger_ui={trigger_ui_index}): {len(actions)} actions, "
            f"start=(page={start_page}, state={start_state}), end=(page={end_page_index}, state={end_state_index})", "blue")

        # 페이지 그래프 업데이트
        if end_page_index != start_page:
            if start_page not in self.page_graph:
                self.page_graph[start_page] = []
            if (end_page_index, subtask_name) not in self.page_graph[start_page]:
                self.page_graph[start_page].append((end_page_index, subtask_name))

        # 메모리에 저장 (mark_subtask_explored_multistep 호출 - state 정보 포함)
        if self.memory and success and len(actions) > 0:
            self.memory.mark_subtask_explored_multistep(
                page_index=start_page,
                subtask_name=subtask_name,
                subtask_info=subtask_info,
                actions=actions,
                trigger_ui_index=trigger_ui_index,
                start_page=start_page,
                end_page=end_page_index,
                start_state=start_state,
                end_state=end_state_index
            )

        # 탐색 상태 초기화
        self.current_exploring_subtask = None
        self.current_exploration_actions = []
        self.current_exploration_step = 0
        self.current_exploration_start_page = None
        self.current_exploration_start_state = None
        self.current_exploration_trigger_ui = -1

    def _get_bfs_action(self, parsed_xml, encoded_xml, current_page_index, current_state_index):
        """BFS: 큐 기반 너비 우선 탐색 + 네비게이션 (Multi-step 서브태스크 지원)"""

        # 현재 진행 중인 Multi-step 서브태스크가 있으면 계속 진행
        if self.current_exploring_subtask is not None:
            return self._continue_subtask_exploration(parsed_xml, encoded_xml, current_page_index, current_state_index)

        # 네비게이션 계획이 있으면 실행
        if self.navigation_plan:
            return self._execute_navigation_step(parsed_xml, encoded_xml, current_page_index)

        while self.exploration_queue:
            target_page, target_state, subtask_info = self.exploration_queue[0]

            # 다른 페이지나 state면 네비게이션 필요
            if target_page != current_page_index or target_state != current_state_index:
                path = self._find_path_to_page(current_page_index, target_page)

                if path:
                    log(f"BFS: Found path from page {current_page_index} to page {target_page} state {target_state}: {path}", "cyan")
                    self.navigation_plan = path
                    return self._execute_navigation_step(parsed_xml, encoded_xml, current_page_index)
                else:
                    log(f"BFS: No path found from page {current_page_index} to page {target_page} state {target_state}, skipping", "yellow")
                    self.exploration_queue.pop(0)
                    continue

            self.exploration_queue.pop(0)

            # 이미 탐색한 (subtask_name, trigger_ui_index) 조합 스킵
            subtask_name = subtask_info['name']
            trigger_ui_index = subtask_info.get('trigger_ui_index', -1)
            page_state_key = (target_page, target_state)
            if (subtask_name, trigger_ui_index) in self.explored_subtasks.get(page_state_key, []):
                continue

            # 새 서브태스크 탐색 시작
            log(f"BFS: Starting multi-step exploration of subtask '{subtask_name}' (trigger_ui={trigger_ui_index}) on page {current_page_index} state {current_state_index}", "cyan")
            return self._start_subtask_exploration(parsed_xml, encoded_xml, current_page_index, current_state_index, subtask_info)

        # ===== GLOBAL EXPLORATION LOGIC =====
        # Local queue is empty - check if exploration is globally complete
        log("BFS: Local queue empty, checking for global unexplored subtasks...", "yellow")

        # 1. Global 완료 확인
        if self._is_global_exploration_complete():
            log("BFS: Global exploration complete!", "green")
            return None

        # 2. 모든 페이지에서 unexplored subtask 찾기 (서브태스크 정보 포함)
        unexplored_items = self._find_all_pages_with_unexplored_subtasks_info()

        if not unexplored_items:
            log("BFS: No unexplored items found (possible data inconsistency)", "yellow")
            return None

        # 3. 가장 가까운 unexplored 페이지 찾기
        nearest_page, nearest_subtask_info, path = self._find_nearest_unexplored_page_info(
            current_page_index,
            unexplored_items
        )

        if nearest_page is None:
            log("BFS: No reachable unexplored pages found", "yellow")
            return None

        log(f"BFS: Nearest unexplored page is {nearest_page} with subtask '{nearest_subtask_info['name']}'", "cyan")

        # 4. 해당 페이지의 모든 unexplored item을 queue에 추가
        for page_idx, subtask_info in unexplored_items:
            if page_idx == nearest_page:
                # 중복 체크
                already_in_queue = any(
                    p == nearest_page and s['name'] == subtask_info['name']
                    for p, s in self.exploration_queue
                )
                if not already_in_queue:
                    self.exploration_queue.append((nearest_page, subtask_info))

        log(f"BFS: Added items from page {nearest_page} to queue", "cyan")

        # 5. 해당 페이지로 navigation
        if nearest_page != current_page_index:
            if path:
                log(f"BFS: Navigating to page {nearest_page} via path: {path}", "cyan")
                self.navigation_plan = path
                return self._execute_navigation_step(parsed_xml, encoded_xml, current_page_index)
            else:
                log(f"BFS: No path to page {nearest_page}, exploration may be incomplete", "red")
                return None

        # 이미 해당 페이지/state에 있으면 재귀 호출로 queue 처리
        return self._get_bfs_action(parsed_xml, encoded_xml, current_page_index, current_state_index)

    def _get_greedy_bfs_action(self, parsed_xml, encoded_xml, current_page_index, current_state_index):
        """Greedy-BFS: BFS로 가장 가까운 unexplored 서브태스크 탐색 (Multi-step 지원)"""

        # 현재 진행 중인 Multi-step 서브태스크가 있으면 계속 진행
        if self.current_exploring_subtask is not None:
            return self._continue_subtask_exploration(parsed_xml, encoded_xml, current_page_index, current_state_index)

        # 네비게이션 계획이 있으면 실행
        if self.navigation_plan:
            return self._execute_navigation_step(parsed_xml, encoded_xml, current_page_index)

        # BFS로 가장 가까운 unexplored 서브태스크 찾기 (subtask_info 반환)
        target_page, target_state, target_subtask_info, path = self._find_nearest_unexplored_info(current_page_index, current_state_index)

        if target_page is None:
            # 모든 서브태스크 탐색 완료
            log("Greedy-BFS: All subtasks explored", "green")
            return None

        subtask_name = target_subtask_info['name']
        log(f"Greedy-BFS: Nearest unexplored is '{subtask_name}' on page {target_page} state {target_state}", "cyan")

        # 현재 페이지/state가 아니면 네비게이션 필요
        if path:
            log(f"Greedy-BFS: Need to navigate via path: {path}", "cyan")
            self.navigation_plan = path
            return self._execute_navigation_step(parsed_xml, encoded_xml, current_page_index)

        # unexplored 리스트에서 제거
        page_state_key = (current_page_index, current_state_index)
        if page_state_key in self.unexplored_subtasks:
            self.unexplored_subtasks[page_state_key] = [
                s for s in self.unexplored_subtasks[page_state_key]
                if s['name'] != subtask_name
            ]

        # 새 서브태스크 탐색 시작
        log(f"Greedy-BFS: Starting multi-step exploration of subtask '{subtask_name}' on page {current_page_index} state {current_state_index}", "cyan")
        return self._start_subtask_exploration(parsed_xml, encoded_xml, current_page_index, current_state_index, target_subtask_info)

    def _get_greedy_dfs_action(self, parsed_xml, encoded_xml, current_page_index, current_state_index):
        """Greedy-DFS: DFS로 가장 깊은 unexplored 서브태스크 탐색 (Multi-step 지원)"""

        # 현재 진행 중인 Multi-step 서브태스크가 있으면 계속 진행
        if self.current_exploring_subtask is not None:
            return self._continue_subtask_exploration(parsed_xml, encoded_xml, current_page_index, current_state_index)

        # 네비게이션 계획이 있으면 실행
        if self.navigation_plan:
            return self._execute_navigation_step(parsed_xml, encoded_xml, current_page_index)

        # DFS로 가장 깊은 unexplored 서브태스크 찾기 (subtask_info 반환)
        target_page, target_state, target_subtask_info, path = self._find_deepest_unexplored_info(current_page_index, current_state_index)

        if target_page is None:
            # 모든 서브태스크 탐색 완료
            log("Greedy-DFS: All subtasks explored", "green")
            return None

        subtask_name = target_subtask_info['name']
        log(f"Greedy-DFS: Deepest unexplored is '{subtask_name}' on page {target_page} state {target_state}", "cyan")

        # 현재 페이지/state가 아니면 네비게이션 필요
        if path:
            log(f"Greedy-DFS: Need to navigate via path: {path}", "cyan")
            self.navigation_plan = path
            return self._execute_navigation_step(parsed_xml, encoded_xml, current_page_index)

        # unexplored 리스트에서 제거
        page_state_key = (current_page_index, current_state_index)
        if page_state_key in self.unexplored_subtasks:
            self.unexplored_subtasks[page_state_key] = [
                s for s in self.unexplored_subtasks[page_state_key]
                if s['name'] != subtask_name
            ]

        # 새 서브태스크 탐색 시작
        log(f"Greedy-DFS: Starting multi-step exploration of subtask '{subtask_name}' on page {current_page_index} state {current_state_index}", "cyan")
        return self._start_subtask_exploration(parsed_xml, encoded_xml, current_page_index, current_state_index, target_subtask_info)

    def _execute_navigation_step(self, parsed_xml, encoded_xml, current_page_index):
        """네비게이션 계획의 다음 단계 실행

        navigation_plan 형식: [(page, action_type, subtask_name), ...]
            - action_type: "forward" (subtask 실행) 또는 "back" (back 액션)
            - subtask_name: forward면 subtask명, back이면 None
        """
        if not self.navigation_plan:
            return None

        step_page, action_type, subtask_name = self.navigation_plan[0]

        # Back 액션 타입인 경우
        if action_type == "back":
            # 0 페이지에서는 back 불가 (앱 종료됨)
            if current_page_index == 0:
                log(f"Navigation: Cannot execute back from page 0, aborting navigation", "red")
                self.navigation_plan = []
                return None
            self.navigation_plan.pop(0)
            if self.traversal_path:
                self.traversal_path.pop()
            log(f"Navigation: Executing back action from page {current_page_index}", "cyan")
            return {"name": "back", "parameters": {}}

        # Forward 액션 타입인 경우
        # 현재 페이지가 단계의 페이지와 다르면 back 필요
        if step_page != current_page_index:
            # 0 페이지에서는 back 불가 (앱 종료됨) - 네비게이션 취소
            if current_page_index == 0:
                log(f"Navigation: Cannot go back from page 0, aborting navigation to page {step_page}", "yellow")
                self.navigation_plan = []
                return None
            if self.traversal_path:
                self.traversal_path.pop()
            log(f"Navigation: Need to go back from page {current_page_index} to reach page {step_page}", "yellow")
            return {"name": "back", "parameters": {}}

        # 서브태스크의 트리거 UI 찾기
        ui_index = self._find_subtask_trigger_ui(current_page_index, subtask_name)

        if ui_index is not None:
            self.navigation_plan.pop(0)
            self.traversal_path.append(current_page_index)
            log(f"Navigation: Clicking subtask '{subtask_name}' (UI {ui_index}) on page {current_page_index}", "cyan")
            return self._create_click_action(parsed_xml, encoded_xml, ui_index, current_page_index, self.current_state_index)

        # UI를 찾지 못하면 네비게이션 계획 초기화
        log(f"Navigation: Could not find UI for subtask '{subtask_name}', aborting navigation", "yellow")
        self.navigation_plan = []
        return None

    def _find_subtask_trigger_ui(self, page_index: int, subtask_name: str) -> int:
        """서브태스크의 트리거 UI 인덱스 찾기"""
        page_data = self.memory.page_db.loc[self.memory.page_db['index'] == page_index]
        if page_data.empty:
            return None

        trigger_uis = json.loads(page_data.iloc[0]['trigger_uis'])

        if subtask_name in trigger_uis:
            ui_list = trigger_uis[subtask_name]
            if ui_list:
                return ui_list[0].get('index')

        return None

    def _create_click_action(self, parsed_xml, encoded_xml, ui_index, page_index, state_index=0):
        """클릭 액션 생성 및 추적 변수 설정"""
        root = ET.fromstring(parsed_xml)
        for elem in root.iter():
            if elem.get('index') == str(ui_index):
                if elem.get('bounds'):
                    action = {"name": "click", "parameters": {"index": str(ui_index)}}
                    self.last_explored_page_index = page_index
                    self.last_explored_state_index = state_index  # [NEW]
                    self.last_explored_ui_index = ui_index
                    self.last_explored_action = action
                    self.last_explored_screen = encoded_xml
                    return action
        return None

    def record_back_transition(self, from_page: int, to_page: int):
        """back 액션으로 from_page에서 to_page로 이동한 기록 저장

        Navigation 경로 계산 시 back edge도 활용할 수 있도록 캐시합니다.

        Args:
            from_page: back 액션 수행 전 페이지
            to_page: back 액션 수행 후 도착한 페이지
        """
        if from_page == to_page:
            return

        if from_page not in self.back_edges:
            self.back_edges[from_page] = []

        if to_page not in self.back_edges[from_page]:
            self.back_edges[from_page].append(to_page)
            log(f"Recorded back edge: {from_page} -> {to_page}", "cyan")

    def mark_last_action_explored(self, end_page: int = -1, end_state: int = 0):
        """마지막으로 클릭한 서브태스크를 explored로 마킹 및 액션 저장 (화면 전환 후 호출)

        화면 전환이 성공적으로 이루어진 후, 이전에 클릭한 UI에 해당하는
        서브태스크를 explored로 표시하고 subtasks.csv와 actions.csv에 저장합니다.

        Args:
            end_page: 서브태스크 종료 페이지 인덱스 (화면 전환 후 페이지)
            end_state: 서브태스크 종료 state 인덱스 (화면 전환 후 state) [NEW]
        """
        if self.last_explored_page_index is None or self.last_explored_ui_index is None:
            return

        if self.memory is None:
            return

        start_page = self.last_explored_page_index
        start_state = self.last_explored_state_index if self.last_explored_state_index is not None else 0

        # STEP 1: 페이지 데이터에서 trigger_uis 정보 가져오기
        page_data = self.memory.page_db.loc[self.memory.page_db['index'] == start_page]
        if page_data.empty:
            self._reset_explore_tracking()
            return

        trigger_uis = json.loads(page_data.iloc[0]['trigger_uis'])

        # STEP 2: 클릭한 UI가 속한 서브태스크 찾기 (실제 subtask 이름 확인)
        found_subtask_name = None
        found_ui_info = None

        for subtask_name, ui_list in trigger_uis.items():
            for ui_info in ui_list:
                if ui_info.get('index') == self.last_explored_ui_index:
                    found_subtask_name = subtask_name
                    found_ui_info = ui_info
                    break
            if found_subtask_name:
                break

        # STEP 3: 페이지 그래프 업데이트 (실제 subtask 이름으로 업데이트)
        if end_page != -1 and end_page != start_page and found_subtask_name:
            if start_page not in self.page_graph:
                self.page_graph[start_page] = []

            # 중복 edge 체크 (동일한 subtask로 가는 edge가 이미 있는지 확인)
            existing_edges = [(p, s) for p, s in self.page_graph[start_page]]

            if (end_page, found_subtask_name) not in existing_edges:
                self.page_graph[start_page].append((end_page, found_subtask_name))
                log(f"Page graph updated: {start_page} -> {end_page} via '{found_subtask_name}'", "blue")

        # STEP 4: Greedy 모드 - 새로운 페이지의 unexplored 서브태스크 로드
        if hasattr(self, 'exploration_algorithm') and self.exploration_algorithm in ["GREEDY_BFS", "GREEDY_DFS"] and end_page != -1:
            self._load_page_unexplored_subtasks(end_page, end_state)

        # STEP 5: 서브태스크를 explored로 마킹 + 액션 저장 (state 정보 포함)
        if found_subtask_name:
            # trigger_ui_index는 last_explored_ui_index와 동일
            trigger_ui_index = self.last_explored_ui_index if self.last_explored_ui_index is not None else -1
            self.memory.mark_subtask_explored(
                start_page,
                found_subtask_name,
                found_ui_info,
                self.last_explored_action,   # 액션 전달
                self.last_explored_screen,   # 화면 XML 전달
                trigger_ui_index=trigger_ui_index,  # trigger UI 인덱스 전달
                end_page=end_page,           # 종료 페이지
                start_state=start_state,     # [NEW] 시작 state
                end_state=end_state          # [NEW] 종료 state
            )
            log(f"Marked subtask '{found_subtask_name}' (trigger_ui={trigger_ui_index}) as explored "
                f"on page {start_page} state {start_state} -> page {end_page} state {end_state}", "green")

        # STEP 6: 추적 변수 초기화
        self._reset_explore_tracking()

    def _load_page_unexplored_subtasks(self, page_index: int, state_index: int):
        """특정 (page, state)의 unexplored 서브태스크 로드 (모든 trigger UI별로)"""
        page_path = os.path.join(self.memory.page_database_path, str(page_index))
        state_path = os.path.join(page_path, str(state_index))
        available_file = os.path.join(state_path, "available_subtasks.csv")

        if os.path.exists(available_file):
            try:
                available_df = pd.read_csv(available_file)
                unexplored_df = available_df[available_df['exploration'] == 'unexplored']

                if not unexplored_df.empty:
                    # pages.csv에서 trigger_uis 가져오기
                    page_data = self.memory.page_db.loc[self.memory.page_db['index'] == page_index]
                    if page_data.empty:
                        return

                    trigger_uis = json.loads(page_data.iloc[0]['trigger_uis'])
                    subtask_infos = []
                    page_state_key = (page_index, state_index)

                    for _, row in unexplored_df.iterrows():
                        subtask_name = row['name']
                        if subtask_name in trigger_uis and trigger_uis[subtask_name]:
                            params = row.get('parameters', {})
                            if isinstance(params, str):
                                try:
                                    params = json.loads(params)
                                except (json.JSONDecodeError, TypeError):
                                    params = {}

                            # 모든 trigger UI에 대해 별도의 subtask_info 생성
                            for ui_info in trigger_uis[subtask_name]:
                                trigger_ui_idx = ui_info.get('index', -1)

                                # 이미 탐색된 (subtask, trigger_ui) 조합 스킵
                                if (subtask_name, trigger_ui_idx) in self.explored_subtasks.get(page_state_key, []):
                                    continue

                                subtask_info = {
                                    'name': subtask_name,
                                    'description': row.get('description', ''),
                                    'parameters': params,
                                    'trigger_ui_index': trigger_ui_idx,
                                    'trigger_ui_info': ui_info
                                }
                                subtask_infos.append(subtask_info)

                    if subtask_infos:
                        self.unexplored_subtasks[page_state_key] = subtask_infos
                        log(f"Loaded {len(subtask_infos)} unexplored subtask-trigger combinations for page {page_index} state {state_index}", "blue")
            except Exception as e:
                log(f"Error reading available_subtasks.csv for page {page_index} state {state_index}: {e}", "yellow")

    def _is_global_exploration_complete(self) -> bool:
        """모든 페이지의 모든 subtask가 explored인지 확인

        Returns:
            bool: True if all subtasks are explored, False otherwise
        """
        pages_dir = self.memory.page_database_path
        if not os.path.exists(pages_dir):
            return True  # 페이지가 없으면 탐색 완료로 간주

        # 모든 페이지 디렉토리 순회
        for page_folder in os.listdir(pages_dir):
            try:
                page_index = int(page_folder)
            except ValueError:
                continue  # 숫자가 아닌 폴더는 스킵

            page_path = os.path.join(pages_dir, page_folder)
            available_file = os.path.join(page_path, "available_subtasks.csv")

            if os.path.exists(available_file):
                try:
                    available_df = pd.read_csv(available_file)

                    # unexplored subtask가 있는지 확인
                    unexplored_count = (available_df['exploration'] == 'unexplored').sum()

                    if unexplored_count > 0:
                        unexplored_names = available_df[available_df['exploration'] == 'unexplored']['name'].tolist()
                        log(f"Page {page_index} has {unexplored_count} unexplored subtasks: {unexplored_names}", "yellow")
                        return False  # Unexplored subtask 발견

                except Exception as e:
                    log(f"Error checking available_subtasks.csv for page {page_folder}: {e}", "yellow")

        log("Global exploration complete: All subtasks explored!", "green")
        return True  # 모든 페이지의 모든 subtask가 explored

    def _find_all_pages_with_unexplored_subtasks(self) -> list:
        """Unexplored subtask가 있는 모든 페이지 찾기

        Returns:
            list: [(page_index, subtask_name, ui_index), ...] 형태의 리스트
        """
        unexplored_items = []
        pages_dir = self.memory.page_database_path

        if not os.path.exists(pages_dir):
            return unexplored_items

        # 모든 페이지 스캔
        for page_folder in os.listdir(pages_dir):
            try:
                page_index = int(page_folder)
            except ValueError:
                continue

            page_path = os.path.join(pages_dir, page_folder)
            available_file = os.path.join(page_path, "available_subtasks.csv")

            if os.path.exists(available_file):
                try:
                    available_df = pd.read_csv(available_file)
                    unexplored_subtasks = available_df[
                        available_df['exploration'] == 'unexplored'
                    ]['name'].tolist()

                    if unexplored_subtasks:
                        # pages.csv에서 trigger_uis 가져오기
                        page_data = self.memory.page_db.loc[self.memory.page_db['index'] == page_index]

                        if not page_data.empty:
                            trigger_uis = json.loads(page_data.iloc[0]['trigger_uis'])

                            # 각 unexplored subtask의 UI 인덱스 찾기
                            for subtask_name in unexplored_subtasks:
                                if subtask_name in trigger_uis:
                                    ui_list = trigger_uis[subtask_name]
                                    if ui_list:
                                        ui_index = ui_list[0].get('index')
                                        if ui_index is not None:
                                            unexplored_items.append((page_index, subtask_name, ui_index))

                except Exception as e:
                    log(f"Error reading page {page_folder}: {e}", "yellow")

        log(f"Found {len(unexplored_items)} unexplored items across all pages", "cyan")
        return unexplored_items

    def _find_nearest_unexplored_page(self, current_page: int, unexplored_items: list) -> tuple:
        """BFS를 사용해 가장 가까운 unexplored 페이지 찾기

        Args:
            current_page: 현재 페이지 인덱스
            unexplored_items: [(page_index, subtask_name, ui_index), ...] 리스트

        Returns:
            tuple: (page_index, subtask_name, ui_index, path) 또는 (None, None, None, None)
                   path는 [(page, subtask), ...] 형태로 목적지까지의 경로
        """
        # Unexplored item이 있는 페이지들의 집합
        unexplored_pages = set(page_idx for page_idx, _, _ in unexplored_items)

        # 현재 페이지에 unexplored가 있으면 바로 반환
        if current_page in unexplored_pages:
            for page_idx, subtask_name, ui_idx in unexplored_items:
                if page_idx == current_page:
                    return (current_page, subtask_name, ui_idx, [])

        # BFS로 가장 가까운 unexplored 페이지 찾기
        queue = deque([(current_page, [])])
        visited = {current_page}

        while queue:
            page, path = queue.popleft()

            # 현재 페이지의 이웃 확인
            if page in self.page_graph:
                for next_page, subtask_name in self.page_graph[page]:
                    if next_page in visited:
                        continue

                    new_path = path + [(page, subtask_name)]

                    # 이 페이지에 unexplored item이 있는지 확인
                    if next_page in unexplored_pages:
                        # 해당 페이지의 첫 번째 unexplored item 반환
                        for p_idx, st_name, ui_idx in unexplored_items:
                            if p_idx == next_page:
                                return (next_page, st_name, ui_idx, new_path)

                    visited.add(next_page)
                    queue.append((next_page, new_path))

        # 도달 가능한 unexplored 페이지가 없음
        log(f"Could not find path to any unexplored page from {current_page}", "red")
        log(f"Unexplored pages: {unexplored_pages}, Visited pages: {visited}", "red")
        return (None, None, None, None)

    def _find_all_pages_with_unexplored_subtasks_info(self) -> list:
        """Unexplored subtask가 있는 모든 페이지 찾기 (subtask_info 포함)

        Returns:
            list: [(page_index, subtask_info), ...] 형태의 리스트
        """
        unexplored_items = []
        pages_dir = self.memory.page_database_path

        if not os.path.exists(pages_dir):
            return unexplored_items

        # 모든 페이지 스캔
        for page_folder in os.listdir(pages_dir):
            try:
                page_index = int(page_folder)
            except ValueError:
                continue

            page_path = os.path.join(pages_dir, page_folder)
            available_file = os.path.join(page_path, "available_subtasks.csv")

            if os.path.exists(available_file):
                try:
                    available_df = pd.read_csv(available_file)
                    unexplored_df = available_df[available_df['exploration'] == 'unexplored']

                    if not unexplored_df.empty:
                        # pages.csv에서 trigger_uis 가져오기
                        page_data = self.memory.page_db.loc[self.memory.page_db['index'] == page_index]

                        if not page_data.empty:
                            trigger_uis = json.loads(page_data.iloc[0]['trigger_uis'])

                            # 각 unexplored subtask의 모든 trigger UI 정보 구성
                            for _, row in unexplored_df.iterrows():
                                subtask_name = row['name']
                                if subtask_name in trigger_uis and trigger_uis[subtask_name]:
                                    params = row.get('parameters', {})
                                    if isinstance(params, str):
                                        try:
                                            params = json.loads(params)
                                        except (json.JSONDecodeError, TypeError):
                                            params = {}

                                    # 모든 trigger UI에 대해 별도의 subtask_info 생성
                                    for ui_info in trigger_uis[subtask_name]:
                                        trigger_ui_idx = ui_info.get('index', -1)

                                        # 이미 탐색된 (subtask, trigger_ui) 조합 스킵
                                        if (subtask_name, trigger_ui_idx) in self.explored_subtasks.get(page_index, []):
                                            continue

                                        subtask_info = {
                                            'name': subtask_name,
                                            'description': row.get('description', ''),
                                            'parameters': params,
                                            'trigger_ui_index': trigger_ui_idx,
                                            'trigger_ui_info': ui_info
                                        }
                                        unexplored_items.append((page_index, subtask_info))

                except Exception as e:
                    log(f"Error reading page {page_folder}: {e}", "yellow")

        log(f"Found {len(unexplored_items)} unexplored items across all pages", "cyan")
        return unexplored_items

    def _find_nearest_unexplored_page_info(self, current_page: int, unexplored_items: list) -> tuple:
        """BFS를 사용해 가장 가까운 unexplored 페이지 찾기 (subtask_info 포함)

        Args:
            current_page: 현재 페이지 인덱스
            unexplored_items: [(page_index, subtask_info), ...] 리스트

        Returns:
            tuple: (page_index, subtask_info, path) 또는 (None, None, None)
                   path는 [(page, subtask), ...] 형태로 목적지까지의 경로
        """
        # Unexplored item이 있는 페이지들의 집합
        unexplored_pages = set(page_idx for page_idx, _ in unexplored_items)

        # 현재 페이지에 unexplored가 있으면 바로 반환
        if current_page in unexplored_pages:
            for page_idx, subtask_info in unexplored_items:
                if page_idx == current_page:
                    return (current_page, subtask_info, [])

        # BFS로 가장 가까운 unexplored 페이지 찾기
        queue = deque([(current_page, [])])
        visited = {current_page}

        while queue:
            page, path = queue.popleft()

            # 현재 페이지의 이웃 확인
            if page in self.page_graph:
                for next_page, subtask_name in self.page_graph[page]:
                    if next_page in visited:
                        continue

                    new_path = path + [(page, subtask_name)]

                    # 이 페이지에 unexplored item이 있는지 확인
                    if next_page in unexplored_pages:
                        # 해당 페이지의 첫 번째 unexplored item 반환
                        for p_idx, subtask_info in unexplored_items:
                            if p_idx == next_page:
                                return (next_page, subtask_info, new_path)

                    visited.add(next_page)
                    queue.append((next_page, new_path))

        # 도달 가능한 unexplored 페이지가 없음
        log(f"Could not find path to any unexplored page from {current_page}", "red")
        return (None, None, None)

    def _find_nearest_unexplored_info(self, current_page: int, current_state: int) -> tuple:
        """BFS로 가장 가까운 unexplored 서브태스크 찾기 (GREEDY_BFS용, subtask_info 포함)

        Returns:
            tuple: (page_index, state_index, subtask_info, path) 또는 (None, None, None, None)
        """
        # 현재 (page, state)에 unexplored가 있으면 바로 반환
        current_key = (current_page, current_state)
        if current_key in self.unexplored_subtasks and self.unexplored_subtasks[current_key]:
            subtask_info = self.unexplored_subtasks[current_key][0]
            return (current_page, current_state, subtask_info, [])

        # BFS로 가장 가까운 unexplored (page, state) 찾기
        # 모든 unexplored (page, state) 찾기
        min_distance = float('inf')
        best_result = (None, None, None, None)

        for page_state_key, subtask_list in self.unexplored_subtasks.items():
            if not subtask_list:
                continue

            target_page, target_state = page_state_key
            path = self._find_path_to_page(current_page, target_page)

            if path is not None:
                distance = len(path)
                if distance < min_distance:
                    min_distance = distance
                    best_result = (target_page, target_state, subtask_list[0], path)

        return best_result

    def _find_deepest_unexplored_info(self, current_page: int, current_state: int) -> tuple:
        """DFS로 가장 깊은 unexplored 서브태스크 찾기 (GREEDY_DFS용, subtask_info 포함)

        깊이 우선으로 탐색하여 가장 깊은 위치의 unexplored 서브태스크를 찾습니다.

        Returns:
            tuple: (page_index, state_index, subtask_info, path) 또는 (None, None, None, None)
        """
        # 현재 (page, state)에 unexplored가 있으면 바로 반환
        current_key = (current_page, current_state)
        if current_key in self.unexplored_subtasks and self.unexplored_subtasks[current_key]:
            subtask_info = self.unexplored_subtasks[current_key][0]
            return (current_page, current_state, subtask_info, [])

        # DFS로 가장 깊은 unexplored (page, state) 찾기
        # 모든 unexplored (page, state) 찾기
        max_depth = -1
        best_result = (None, None, None, None)

        for page_state_key, subtask_list in self.unexplored_subtasks.items():
            if not subtask_list:
                continue

            target_page, target_state = page_state_key
            path = self._find_path_to_page(current_page, target_page)

            if path is not None:
                depth = len(path)
                if depth > max_depth:
                    max_depth = depth
                    best_result = (target_page, target_state, subtask_list[0], path)

        return best_result

    def _reset_explore_tracking(self):
        """탐색 추적 변수 초기화"""
        self.last_explored_page_index = None
        self.last_explored_state_index = None  # [NEW]
        self.last_explored_ui_index = None
        self.last_explored_action = None
        self.last_explored_screen = None
