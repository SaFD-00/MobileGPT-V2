package com.example.hardcode;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.content.ClipboardManager;
import android.graphics.Path;
import android.graphics.Rect;
import android.os.Bundle;
import android.util.Log;
import android.view.accessibility.AccessibilityNodeInfo;

// 사용자 입력(클릭, 스크롤 등)을 디스패치하는 클래스
public class InputDispatcher {
    private static final String TAG = "MobileGPT_InputDispatcher"; // 로그 태그

    // 제스처 완료 또는 취소 시 호출되는 콜백
    private static AccessibilityService.GestureResultCallback callback = new AccessibilityService.GestureResultCallback() {
        @Override
        public void onCompleted(GestureDescription gestureDescription) {
            super.onCompleted(gestureDescription);
            Log.d(TAG, "제스처가 완료되었습니다.");
        }

        @Override
        public void onCancelled(GestureDescription gestureDescription) {
            super.onCancelled(gestureDescription);
            Log.d(TAG, "제스처가 취소되었습니다.");
        }
    };

    // 클릭 액션을 수행
    public static boolean performClick(AccessibilityService service, AccessibilityNodeInfo node, boolean retry) {
        // 가장 가까운 클릭 가능한 조상 노드를 찾음
        AccessibilityNodeInfo targetNode = nearestClickableNode(node);
        if (targetNode != null) {
            Rect nodeBound = new Rect();
            targetNode.getBoundsInScreen(nodeBound);
            Log.d(TAG, "노드 경계: left=" + nodeBound.left + " top=" + nodeBound.top + " right=" + nodeBound.right + " bottom=" + nodeBound.bottom);
            if (!retry)
                // 재시도가 아니면 일반 클릭 액션 수행
                return targetNode.performAction(AccessibilityNodeInfo.ACTION_CLICK);
            else
                // 재시도인 경우, 좌표를 이용한 강제 클릭 이벤트
                return InputDispatcher.dispatchClick(service, (int)((nodeBound.left+nodeBound.right)/2), (int)((nodeBound.top+nodeBound.bottom)/2), 10);
        }
        else {
            // 클릭 가능한 UI를 찾지 못하면 강제 터치 이벤트 발생
            Log.e(TAG, "클릭할 UI를 찾지 못했습니다. 터치 이벤트를 강제 실행합니다.");
            Rect nodeBound = new Rect();
            node.getBoundsInScreen(nodeBound);
            Log.d(TAG, "노드 경계: left=" + nodeBound.left + " top=" + nodeBound.top + " right=" + nodeBound.right + " bottom=" + nodeBound.bottom);
            return InputDispatcher.dispatchClick(service, (int)((nodeBound.left+nodeBound.right)/2), (int)((nodeBound.top+nodeBound.bottom)/2), 10);
        }
    }

    // 롱클릭 액션을 수행
    public static boolean performLongClick(AccessibilityService service, AccessibilityNodeInfo node){
        AccessibilityNodeInfo targetNode = nearestLongClickableNode(node);
        if (targetNode!=null) {
                return targetNode.performAction(AccessibilityNodeInfo.ACTION_LONG_CLICK);
        } else {
            Log.e(TAG, "롱클릭할 UI를 찾지 못했습니다. 롱터치 이벤트를 강제 실행합니다.");
            Rect nodeBound = new Rect();
            node.getBoundsInScreen(nodeBound);
            return InputDispatcher.dispatchClick(service, (int)((nodeBound.left+nodeBound.right)/2), (int)((nodeBound.top+nodeBound.bottom)/2), 2000);
        }
    }

    // 스크롤 액션을 수행
    public static boolean performScroll(AccessibilityNodeInfo node, String direction) {
        AccessibilityNodeInfo targetNode = nearestScrollalbeNode(node);
        if (targetNode!=null) {
            if (direction.equals("down"))
                return targetNode.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD);
            else
                return targetNode.performAction(AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD);
        } else {
            Log.e(TAG, "스크롤할 UI를 찾지 못했습니다.");
            return false;
        }
    }

    // 텍스트 입력 액션을 수행
    public static boolean performTextInput(AccessibilityService service, ClipboardManager clipboard, AccessibilityNodeInfo node, String text) {
        if (node.isEditable()) {
            // 직접 텍스트 주입 방식
            Bundle arguments = new Bundle();
            arguments.putCharSequence(AccessibilityNodeInfo
                    .ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text);
            return node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments);

        } else {
            // 편집 불가능한 경우 클릭 시도
            return performClick(service, node, false);
        }
    }

    // 뒤로가기 액션을 수행
    public static boolean performBack(AccessibilityService service) {
        return service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK);
    }

    // 홈 버튼 액션을 수행
    public static boolean performHome(AccessibilityService service) {
        return service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME);
    }

    // 특정 좌표에 클릭 제스처를 전달
    public static boolean dispatchClick(AccessibilityService service, float x , float y, int duration) {
        int id = service.getResources().getIdentifier("status_bar_height", "dimen", "android");
        int statusbar_height = service.getResources().getDimensionPixelSize(id);

        Log.d(TAG, String.format("x=%f, y=%f에 대한 클릭 제스처",x,y));
        boolean result = service.dispatchGesture(createClick(x, y, duration), callback, null);
        Log.d(TAG, "제스처 전달 결과: " + result);
        return result;

    }

    // 가장 가까운 클릭 가능한 노드를 찾는 헬퍼 메서드
    private static AccessibilityNodeInfo nearestClickableNode(AccessibilityNodeInfo node) {
        if (node == null)
            return null;

        if (node.isClickable()) {
            return node;
        } else {
            // 현재 노드가 클릭 불가능하면 null 반환 (조상 탐색 안함)
            return null;
        }
    }

    // 가장 가까운 롱클릭 가능한 노드를 찾는 헬퍼 메서드
    private static AccessibilityNodeInfo nearestLongClickableNode(AccessibilityNodeInfo node) {
        if (node == null)
            return null;

        if (node.isLongClickable()) {
            return node;
        } else {
            // 현재 노드가 롱클릭 불가능하면 null 반환 (조상 탐색 안함)
            return null;
        }
    }

    // 스크롤 가능한 가장 가까운 노드를 찾는 헬퍼 메서드 (부모 노드까지 재귀적으로 탐색)
    private static AccessibilityNodeInfo nearestScrollalbeNode(AccessibilityNodeInfo node) {
        if (node == null)
            return null;

        if (node.isScrollable()) {
            return node;
        } else {
            return nearestScrollalbeNode(node.getParent());
        }
    }

    // 클릭 제스처를 생성
    private static GestureDescription createClick(float x, float y, int duration) {
        final int DURATION = duration;

        Path clickPath = new Path();
        clickPath.moveTo(x, y);
        GestureDescription.StrokeDescription clickStroke =
                new GestureDescription.StrokeDescription(clickPath, 0, DURATION);
        GestureDescription.Builder clickBuilder = new GestureDescription.Builder();
        clickBuilder.addStroke(clickStroke);
        return clickBuilder.build();
    }
}
