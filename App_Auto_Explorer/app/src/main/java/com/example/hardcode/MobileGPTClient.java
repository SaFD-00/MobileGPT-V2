package com.example.hardcode;

import android.graphics.Bitmap;
import android.util.Log;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

// 서버와 통신하는 클라이언트 클래스
public class MobileGPTClient {
    private static final String TAG = "MobileGPT_CLIENT"; // 로그 태그
    private String serverAddress; // 서버 주소
    private int serverPort; // 서버 포트
    private Socket socket; // 클라이언트 소켓
    private DataOutputStream dos; // 데이터 출력 스트림

    // 생성자
    public MobileGPTClient(String serverAddress, int serverPort) {
        this.serverAddress = serverAddress;
        this.serverPort = serverPort;
    }

    // 서버에 연결
    public void connect() throws IOException{
        socket = new Socket(serverAddress, serverPort);
        dos = new DataOutputStream(socket.getOutputStream());
    }

    // 서버와 연결 해제
    public void disconnect() {
        try {
            if (socket != null) {
                dos.close();
                socket.close();
            }
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
    }

    // 현재 앱의 패키지 이름을 서버로 전송
    public void sendPackageName(String packageName) {
        try {
            if (socket != null) {
                dos.writeByte('A'); // 데이터 종류 식별자 (App)
                dos.write((packageName+"\n").getBytes("UTF-8"));
                dos.flush();

                Log.v(TAG, "패키지 "+packageName+"가 성공적으로 전송되었습니다.");
            }
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
    }

    // 탐색 종료 신호를 서버로 전송
    public void sendFinish() {
        try {
            if (socket != null) {
                dos.writeByte('F'); // 데이터 종류 식별자 (Finish)
                dos.flush();
                disconnect(); // 전송 후 연결 해제
            }
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
    }

    // 스크린샷 이미지를 서버로 전송
    public void sendScreenshot(Bitmap bitmap) {
        try {
            if (socket!=null) {
                dos.writeByte('S'); // 데이터 종류 식별자 (Screenshot)

                // 비트맵을 JPEG 형식의 바이트 배열로 압축
                ByteArrayOutputStream byteArrayOutputStream = new ByteArrayOutputStream();
                bitmap.compress(Bitmap.CompressFormat.JPEG, 100, byteArrayOutputStream);
                byte[] byteArray = byteArrayOutputStream.toByteArray();

                int size = byteArray.length;
                String file_size = size+"\n";
                dos.write(file_size.getBytes()); // 이미지 크기 전송

                // 이미지 데이터 전송
                dos.write(byteArray);
                dos.flush();

                Log.v(TAG, "스크린샷이 성공적으로 전송되었습니다.");
            }
        } catch (IOException e) {
            Log.e(TAG, "서버가 오프라인입니다.");
        }
    }

    // XML 문자열을 서버로 전송
    public void sendXML(String xml) {
        try {
            if (socket!= null) {
                dos.writeByte('X'); // 데이터 종류 식별자 (XML)
                int size = xml.getBytes("UTF-8").length;
                String file_size = size+"\n";
                dos.write(file_size.getBytes()); // XML 크기 전송

                // XML 데이터 전송
                dos.write(xml.getBytes(StandardCharsets.UTF_8));
                dos.flush();

                Log.v(TAG, "XML이 성공적으로 전송되었습니다.");
            }
        } catch (IOException e) {
            Log.e(TAG, "서버가 오프라인입니다.");
        }
    }

    // 서버로부터 메시지를 비동기적으로 수신하는 메서드
    public void receiveMessages(OnMessageReceived onMessageReceived) {
        new Thread(() -> {
            try {
                BufferedReader reader = new BufferedReader(new InputStreamReader(socket.getInputStream()));
                String message;
                // 소켓 스트림에서 한 줄씩 메시지를 읽음
                while ((message = reader.readLine()) != null) {
                    // 콜백을 통해 수신된 메시지 전달
                    onMessageReceived.onReceived(message);
                }
            } catch (IOException e) {
                Log.e(TAG, "메시지 수신 중 오류 발생: " + e.getMessage());
                e.printStackTrace();
            }
        }).start();
    }

    // 메시지 수신 시 호출될 콜백 인터페이스
    public interface OnMessageReceived {
        void onReceived(String message);
    }

}

