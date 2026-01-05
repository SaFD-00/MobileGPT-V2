package com.example.hardcode.widgets;

import android.annotation.SuppressLint;
import android.content.Context;
import android.graphics.PixelFormat;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.LayoutInflater;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.TextView;

import com.example.hardcode.MobileGPTAccessibilityService;
import com.example.hardcode.MobileGPTClient;
import com.example.hardcode.R;
import com.google.android.material.floatingactionbutton.ExtendedFloatingActionButton;
import com.google.android.material.floatingactionbutton.FloatingActionButton;

import java.util.ArrayList;

// 화면에 떠다니는 플로팅 버튼을 관리하는 클래스
public class FloatingButtonManager implements View.OnClickListener{
    public static String MobileGPT_TAG = "MobileGPT(FloatingButton)"; // 로그 태그
    // 사용자가 FAB를 탭할 때 의도하지 않은 약간의 드래그가 발생할 수 있으므로 이를 고려해야 합니다.
    private final static float CLICK_DRAG_TOLERANCE = 10;
    FrameLayout layout; // 플로팅 버튼의 레이아웃
    private Context mContext;
    private WindowManager windowManager;
    private MobileGPTClient mClient;
    private ExtendedFloatingActionButton mFLoatingButton; // 메인 플로팅 버튼
    public ArrayList<FloatingActionButton> subFabs; // 하위 플로팅 버튼 목록
    public ArrayList<TextView> subFabsText; // 하위 플로팅 버튼 텍스트 목록
    public FloatingActionButton mFinishButton, mCaptureButton, mStartButton; // 시작, 캡처, 종료 버튼
    private TextView mFinishText, mCaptureText, mStartText;
    boolean mIsAllFabsVisible = false; // 모든 하위 버튼이 보이는지 여부

    private mode curMode; // 현재 모드 (AUTO 또는 DEMO)
    private enum mode {AUTO, DEMO}

    private final Handler mainThreadHandler = new Handler(Looper.getMainLooper());

    @SuppressLint("ClickableViewAccessibility")
    public FloatingButtonManager(Context context, MobileGPTClient client){
        curMode = mode.AUTO;
        mContext = context;
        mClient = client;
        windowManager = (WindowManager) mContext.getSystemService(Context.WINDOW_SERVICE);
        layout = new FrameLayout(context);
        // 다른 앱 위에 표시될 수 있도록 WindowManager.LayoutParams 설정
        final WindowManager.LayoutParams params = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
                PixelFormat.TRANSLUCENT);
        params.gravity = Gravity.END | Gravity.CENTER_VERTICAL; // 오른쪽 중앙에 위치

        LayoutInflater inflater = LayoutInflater.from(context);
        inflater.inflate(R.layout.floating_button, layout); // XML 레이아웃 파일 인플레이트
        windowManager.addView(layout, params); // WindowManager에 레이아웃 추가

        mFLoatingButton = layout.findViewById(R.id.fab);

        subFabs = new ArrayList<>();
        subFabsText = new ArrayList<>();

        // 하위 버튼 및 텍스트 초기화
        mFinishButton = (FloatingActionButton) layout.findViewById(R.id.finish_fab);
        subFabs.add(mFinishButton);
        mFinishText = (TextView) layout.findViewById(R.id.finish_text);
        subFabsText.add(mFinishText);

        mCaptureButton = (FloatingActionButton) layout.findViewById(R.id.capture_fab);
        subFabs.add(mCaptureButton);
        mCaptureText = (TextView) layout.findViewById(R.id.capture_text);
        subFabsText.add(mCaptureText);

        mStartButton = (FloatingActionButton) layout.findViewById(R.id.start_fab);
        subFabs.add(mStartButton);
        mStartText = (TextView) layout.findViewById(R.id.start_text);
        subFabsText.add(mStartText);

        shrink(); // 초기 상태는 축소된 상태
        mFLoatingButton.setOnClickListener(this);
        // 메인 버튼 드래그 앤 드롭 기능 구현
        mFLoatingButton.setOnTouchListener(new View.OnTouchListener(){
            private int initialX, initialY;
            private float initialTouchX, initialTouchY;

            @Override
            public boolean onTouch(View v, MotionEvent event) {
                switch (event.getAction()) {
                    case MotionEvent.ACTION_DOWN:
                        initialX = params.x;
                        initialY = params.y;
                        initialTouchX = event.getRawX();
                        initialTouchY = event.getRawY();
                        return true;
                    case MotionEvent.ACTION_UP:
                        float upRawX = event.getRawX();
                        float upRawY = event.getRawY();

                        float upDX = upRawX - initialTouchX;
                        float upDY = upRawY - initialTouchY;

                        // 드래그 거리가 짧으면 클릭으로 간주
                        if (Math.abs(upDX) < CLICK_DRAG_TOLERANCE && Math.abs(upDY) < CLICK_DRAG_TOLERANCE) {
                            return v.performClick();
                        }
                    case MotionEvent.ACTION_MOVE:
                        // 터치 이동에 따라 버튼 위치 업데이트
                        params.x = initialX - (int) (event.getRawX() - initialTouchX);
                        params.y = initialY + (int) (event.getRawY() - initialTouchY);
                        windowManager.updateViewLayout(layout, params);
                        return true;
                }
                return false;
            }
        });
        layout.setVisibility(View.GONE); // 초기에는 보이지 않음

        // 종료 버튼 클릭 리스너
        mFinishButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                ((MobileGPTAccessibilityService)mContext).finish();
            }
        });

        // 캡처 버튼 클릭 리스너
        mCaptureButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                ((MobileGPTAccessibilityService)mContext).captureScreen();

            }
        });

        // 시작 버튼 클릭 리스너
        mStartButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                ((MobileGPTAccessibilityService)mContext).start();
            }
        });

    }

    // 메인 버튼 클릭 시 확장/축소 토글
    @Override
    public void onClick(View view) {
        if(!mIsAllFabsVisible) {
            extend();
        } else {
            shrink();
        }
    }

    // 플로팅 버튼 레이아웃 숨기기
    public void dismiss(){
        layout.setVisibility(View.GONE);
    }

    // 플로팅 버튼 레이아웃 보이기
    public void show() {
        layout.setVisibility(View.VISIBLE);
    }

    // 하위 버튼들 확장
    private void extend() {
        for (FloatingActionButton fab : subFabs) {
            fab.show();
        }
        for (TextView text : subFabsText) {
            text.setVisibility(View.VISIBLE);
        }
        mFLoatingButton.extend();
        mIsAllFabsVisible = true;
    }

    // 하위 버튼들 축소
    public void shrink() {
        for (FloatingActionButton fab : subFabs) {
            fab.hide();
        }
        for (TextView text : subFabsText) {
            text.setVisibility(View.GONE);
        }
        mFLoatingButton.shrink();
        mIsAllFabsVisible = false;
    }
}
