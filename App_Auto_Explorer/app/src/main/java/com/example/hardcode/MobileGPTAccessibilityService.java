package com.example.hardcode;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.content.ClipboardManager;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Rect;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.Display;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.File;
import java.io.IOException;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import android.view.accessibility.AccessibilityWindowInfo;

import androidx.annotation.NonNull;

import com.example.hardcode.widgets.FloatingButtonManager;
import com.example.hardcode.response.GPTMessage;

// MobileGPT 접근성 서비스: 앱 자동 탐색의 핵심 기능을 수행합니다.
public class MobileGPTAccessibilityService extends AccessibilityService{
    private static final String TAG = "MobileGPT_Service"; // 로그 태그
    private MobileGPTClient mClient; // 서버 통신 클라이언트
    public FloatingButtonManager mFloatingButtonManager; // 플로팅 버튼 UI 매니저
    private HashMap<Integer, AccessibilityNodeInfo> nodeMap; // 현재 화면의 노드 정보를 인덱스와 함께 저장
    private String targetPackageName; // 현재 감지된 앱의 패키지 이름
    private String finalTargetPackageName; // 최종적으로 탐색할 앱의 패키지 이름
    private ExecutorService mExecutorService; // 백그라운드 작업을 위한 스레드 풀
    private final Handler mainThreadHandler = new Handler(Looper.getMainLooper()); // 메인 스레드 핸들러
    private String currentScreenXML = ""; // 현재 화면의 XML 구조
    private Bitmap currentScreenShot = null; // 현재 화면의 스크린샷
    private File fileDirectory; // 파일 저장 디렉토리

    // 자동 탐색 관련 변수들
    private boolean autoExploreMode = false; // 자동 탐색 모드 활성화 여부
    private boolean xmlPending = false; // XML 전송 대기 여부
    private boolean screenNeedUpdate = false; // 화면 업데이트 필요 여부
    private Runnable screenUpdateWaitRunnable; // 화면 업데이트 대기 후 실행될 작업
    private Runnable screenUpdateTimeoutRunnable; // 화면 업데이트 시간 초과 시 실행될 작업
    private Runnable clickRetryRunnable; // 클릭 재시도 작업
    private Runnable actionFailedRunnable; // 액션 실패 시 실행될 작업

    // 접근성 이벤트 발생 시 호출되는 콜백 메서드
    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        // 창 상태 변경 이벤트 발생 시
        if (event.getEventType() == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
            CharSequence packageName = event.getPackageName();
            // 현재 서비스의 패키지가 아닌 경우, 대상 패키지 이름 업데이트
            if (packageName != null && !packageName.equals("com.example.hardcode")) {
                targetPackageName = packageName.toString();
            }
        }

        // 자동 탐색 모드일 때 화면 변경 감지 및 자동 캡처
        if (autoExploreMode &&
            (event.getEventType() == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED ||
             event.getEventType() == AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED) &&
            event.getSource() != null) {

            // 현재 서비스의 패키지에서 발생한 이벤트는 무시
            if (event.getPackageName() != null && event.getPackageName().equals("com.example.hardcode")) {
                return;
            }

            // XML 전송이 대기 중이고 화면 업데이트가 필요한 경우
            if (xmlPending && screenNeedUpdate) {
                // 기존의 콜백들을 모두 제거
                mainThreadHandler.removeCallbacks(clickRetryRunnable);
                mainThreadHandler.removeCallbacks(actionFailedRunnable);
                mainThreadHandler.removeCallbacks(screenUpdateWaitRunnable);
                mainThreadHandler.removeCallbacks(screenUpdateTimeoutRunnable);
                // 3초 후 화면 업데이트 대기 작업 실행
                mainThreadHandler.postDelayed(screenUpdateWaitRunnable, 3000);
                screenNeedUpdate = false;
            }
        }
    }

    // 서비스가 연결되었을 때 호출되는 콜백 메서드
    @Override
    public void onServiceConnected() {
        AccessibilityServiceInfo info = new AccessibilityServiceInfo();

        info.eventTypes = AccessibilityEvent.TYPES_ALL_MASK; // 모든 이벤트 유형 수신
        info.feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC
                | AccessibilityServiceInfo.FEEDBACK_HAPTIC; // 피드백 유형 설정
        info.notificationTimeout = 100; // 알림 시간 초과 (ms)
        // 서비스 플래그 설정: 뷰 ID 보고, 제스처 수행, 스크린샷 캡처 등
        info.flags = AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS
                | AccessibilityServiceInfo.CAPABILITY_CAN_PERFORM_GESTURES
                | AccessibilityServiceInfo.CAPABILITY_CAN_TAKE_SCREENSHOT
                | AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS
                | AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;

        mExecutorService = Executors.newSingleThreadExecutor(); // 단일 스레드 실행자 생성

        mFloatingButtonManager = new FloatingButtonManager(this, mClient); // 플로팅 버튼 매니저 초기화
        mFloatingButtonManager.show(); // 플로팅 버튼 보이기

        // 자동 탐색을 위한 화면 업데이트 Runnable 초기화
        screenUpdateWaitRunnable = new Runnable() {
            @Override
            public void run() {
                Log.d(TAG, "화면 업데이트 대기 완료, 자동 캡처 시작");
                mainThreadHandler.removeCallbacks(screenUpdateTimeoutRunnable); // 타임아웃 콜백 제거
                autoCapture(); // 자동 캡처 실행
            }
        };

        screenUpdateTimeoutRunnable = new Runnable() {
            @Override
            public void run() {
                Log.d(TAG, "화면 업데이트 시간 초과, 자동 캡처 시작");
                mainThreadHandler.removeCallbacks(screenUpdateWaitRunnable); // 대기 콜백 제거
                autoCapture(); // 자동 캡처 실행
            }
        };
    }

    // 활성 앱의 루트 노드를 가져오는 메서드
    private AccessibilityNodeInfo getRootForActiveApp(){
        List<AccessibilityWindowInfo> windows = getWindows(); // 현재 화면의 모든 창 정보 가져오기

        for (AccessibilityWindowInfo window : windows) {
            AccessibilityNodeInfo root = window.getRoot();
            if (root != null) {
                // 루트 노드의 패키지 이름이 목표 패키지 이름과 같으면 반환
                if (root.getPackageName().equals(finalTargetPackageName)) {
                    return root;
                }
            }
        }
        Log.d(TAG, "이 화면에서 적절한 루트 노드를 찾지 못했습니다.");
        return null;
    }

    // 자동 탐색 시작
    public void start() {
        reset(); // 상태 초기화
        autoExploreMode = true; // 자동 탐색 모드 활성화
        xmlPending = false;
        screenNeedUpdate = false;
        mExecutorService.execute(this::initNetworkConnection); // 네트워크 연결 초기화
        mExecutorService.execute(()-> mClient.sendPackageName(targetPackageName)); // 패키지 이름 전송
        finalTargetPackageName = targetPackageName; // 최종 목표 패키지 설정
        Log.d(TAG, "자동 탐색 모드가 시작되었습니다.");
    }

    // 자동 탐색 종료
    public void finish(){
        mExecutorService.execute(()-> mClient.sendFinish()); // 서버에 종료 신호 전송
        mFloatingButtonManager.shrink(); // 플로팅 버튼 축소

    }

    // 수동으로 화면 캡처
    public void captureScreen() {
        Log.d(TAG, "수동 캡처가 실행되었습니다.");
        mFloatingButtonManager.dismiss(); // 플로팅 버튼 숨기기
        saveCurrScreenXML(); // 현재 화면 XML 저장
        saveCurrentScreenShot(); // 현재 화면 스크린샷 저장
    }

    // 자동 화면 캡처
    private void autoCapture() {
        Log.d(TAG, "자동 캡처가 실행되었습니다.");
        xmlPending = false;
        screenNeedUpdate = false;
        saveCurrScreenXML();
        saveCurrentScreenShot();
    }

    // 현재 화면의 XML 레이아웃을 저장
    private void saveCurrScreenXML() {
        nodeMap = new HashMap<>(); // 노드 맵 초기화
        Log.d(TAG, "노드 맵이 갱신되었습니다!");
        AccessibilityNodeInfo rootNode = getRootForActiveApp(); // 활성 앱의 루트 노드 가져오기
        if (rootNode != null) {
            // XML 덤프 실행
            currentScreenXML = AccessibilityNodeInfoDumper.dumpWindow(rootNode, nodeMap, fileDirectory);
        }
    }

    // 현재 화면의 스크린샷을 저장
    private void saveCurrentScreenShot() {
        // 스크린샷 API 호출
        takeScreenshot(Display.DEFAULT_DISPLAY, getMainExecutor(), new TakeScreenshotCallback() {
            @Override
            public void onSuccess(@NonNull ScreenshotResult screenshotResult) {
                Log.d(TAG, "스크린샷 성공!");
                // 하드웨어 버퍼를 비트맵으로 변환
                currentScreenShot = Bitmap.wrapHardwareBuffer(screenshotResult.getHardwareBuffer(),screenshotResult.getColorSpace());
                sendScreen(); // 화면 정보 전송
                mFloatingButtonManager.show(); // 플로팅 버튼 다시 보이기
            }
            @Override
            public void onFailure(int i) {
                Log.i(TAG,"스크린샷 실패, 코드: "+ i);
            }
        });
    }

    // 스크린샷과 XML을 서버로 전송
    private void sendScreen(){
        mExecutorService.execute(()->mClient.sendScreenshot(currentScreenShot));
        mExecutorService.execute(()-> mClient.sendXML(currentScreenXML));
    }

    @Override
    public void onInterrupt() {
        // TODO Auto-generated method stub
        Log.e("TEST", "OnInterrupt");
    }

    // 서비스가 파괴될 때 호출
    @Override
    public void onDestroy() {
        mClient.disconnect();
        mClient = null;
        super.onDestroy();
    }

    // 상태 초기화 (네트워크 연결 해제)
    private void reset() {
        if (mClient != null) {
            mClient.disconnect();
            mClient = null;
        }
    }

    // 네트워크 연결 초기화
    private void initNetworkConnection() {
        mClient = new MobileGPTClient(MobileGPTGlobal.HOST_IP, MobileGPTGlobal.HOST_PORT);
        try {
            mClient.connect(); // 서버에 연결
            // 서버로부터 메시지 수신 시작
            mClient.receiveMessages(message -> {
                new Thread(() -> {
                    if (message != null) {
                        handleResponse(message); // 수신된 메시지 처리
                    }
                }).start();
            });
        } catch (IOException e) {
            Log.e(TAG, "서버가 오프라인입니다.");
        }
    }

    // 서버로부터 받은 응답(명령)을 처리
    private void handleResponse(String message) {
        Log.d(TAG, "수신된 메시지: " + message);

        try {
            GPTMessage gptMessage = new GPTMessage(message); // 메시지 파싱
            String action = gptMessage.getActionName(); // 액션 이름 가져오기
            JSONObject args = gptMessage.getArgs(); // 파라미터 가져오기

            // '뒤로가기' 액션 처리
            if (action.equals("back")) {
                Log.d(TAG, "뒤로가기 액션을 수행합니다.");
                InputDispatcher.performBack(this);
                screenNeedUpdate = true;
                xmlPending = true;
                mainThreadHandler.postDelayed(screenUpdateTimeoutRunnable, 5000); // 5초 후 타임아웃
                return;
            } else if (action.equals("home")) { // '홈' 액션 처리
                Log.d(TAG, "홈 액션을 수행합니다.");
                InputDispatcher.performHome(this);
                screenNeedUpdate = true;
                xmlPending = true;
                mainThreadHandler.postDelayed(screenUpdateTimeoutRunnable, 5000); // 5초 후 타임아웃
                return;
            }

            // 파라미터에서 'index' 가져오기
            int index = -1;
            try {
                index = Integer.parseInt((String) (args.get("index")));
            } catch (ClassCastException e) {
                index = (Integer) args.get("index");
            } catch (JSONException e) {
                Log.e(TAG, "액션에 인덱스가 없습니다.");
                return;
            }

            AccessibilityNodeInfo targetNode = nodeMap.get(index); // 인덱스에 해당하는 노드 찾기

            // 노드를 찾지 못한 경우
            if (targetNode == null) {
                Log.e(TAG, "인덱스 " + index + "에 해당하는 노드를 찾지 못했습니다.");
                Log.d(TAG, "사용 가능한 nodeMap 인덱스:");
                for (Map.Entry<Integer, AccessibilityNodeInfo> entry : nodeMap.entrySet()) {
                    Integer key = entry.getKey();
                    AccessibilityNodeInfo node = entry.getValue();
                    Rect nodeBound = new Rect();
                    node.getBoundsInScreen(nodeBound);
                    Log.d(TAG, "Index: " + key + " - Bound: ["+nodeBound.left+","+nodeBound.top+","+nodeBound.right+","+nodeBound.bottom+"]");
                }
                return;
            }

            boolean action_success = false; // 액션 성공 여부

            // 액션 종류에 따라 분기
            switch (action) {
                case "click":
                    Log.d(TAG, "인덱스 " + index + "에 클릭 액션을 수행합니다.");
                    action_success = InputDispatcher.performClick(this, targetNode, false);
                    Log.d(TAG, "클릭 성공=" + action_success);

                    // 3초 후 클릭 재시도
                    clickRetryRunnable = new Runnable() {
                        @Override
                        public void run() {
                            InputDispatcher.performClick(MobileGPTAccessibilityService.this, targetNode, true);
                        }
                    };
                    mainThreadHandler.postDelayed(clickRetryRunnable, 3000);
                    break;

                case "long-click":
                    Log.d(TAG, "인덱스 " + index + "에 롱클릭 액션을 수행합니다.");
                    action_success = InputDispatcher.performLongClick(this, targetNode);
                    Log.d(TAG, "롱클릭 성공=" + action_success);
                    break;

                case "input":
                    Log.d(TAG, "인덱스 " + index + "에 입력 액션을 수행합니다.");
                    String text = (String) (args.get("input_text"));
                    ClipboardManager clipboard = (ClipboardManager) this.getSystemService(Context.CLIPBOARD_SERVICE);
                    action_success = InputDispatcher.performTextInput(this, clipboard, targetNode, text);
                    Log.d(TAG, "입력 성공=" + action_success);
                    break;

                case "scroll":
                    Log.d(TAG, "인덱스 " + index + "에 스크롤 액션을 수행합니다.");
                    String direction = (String) (args.get("direction"));
                    action_success = InputDispatcher.performScroll(targetNode, direction);
                    Log.d(TAG, "스크롤 성공=" + action_success);
                    break;
            }

            // 액션 수행 후 화면 업데이트 필요 표시
            screenNeedUpdate = true;
            xmlPending = true;
            mainThreadHandler.postDelayed(screenUpdateTimeoutRunnable, 8000); // 8초 후 타임아웃

        } catch (JSONException e) {
            Log.e(TAG, "액션 JSON 파싱 오류: " + e.getMessage());
            e.printStackTrace();
        }
    }
}
