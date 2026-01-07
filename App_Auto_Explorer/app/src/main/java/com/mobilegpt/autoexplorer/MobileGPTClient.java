package com.mobilegpt.autoexplorer;

import android.graphics.Bitmap;
import android.util.Log;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class MobileGPTClient {
    private static final String TAG = "MobileGPT_CLIENT";
    private String serverAddress;
    private int serverPort;
    private Socket socket;
    private DataOutputStream dos;

    public MobileGPTClient(String serverAddress, int serverPort) {
        this.serverAddress = serverAddress;
        this.serverPort = serverPort;
    }

    public void connect() throws IOException {
        socket = new Socket(serverAddress, serverPort);
        dos = new DataOutputStream(socket.getOutputStream());
    }

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

    public void sendPackageName(String packageName) {
        try {
            if (socket != null) {
                dos.writeByte('A');
                dos.write((packageName + "\n").getBytes("UTF-8"));
                dos.flush();
                Log.v(TAG, "Package " + packageName + " sent successfully");
            }
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
    }

    public void sendFinish() {
        try {
            if (socket != null) {
                dos.writeByte('F');
                dos.flush();
                disconnect();
            }
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
    }

    public void sendScreenshot(Bitmap bitmap) {
        try {
            if (socket != null) {
                dos.writeByte('S');

                ByteArrayOutputStream byteArrayOutputStream = new ByteArrayOutputStream();
                bitmap.compress(Bitmap.CompressFormat.JPEG, 100, byteArrayOutputStream);
                byte[] byteArray = byteArrayOutputStream.toByteArray();

                int size = byteArray.length;
                String fileSize = size + "\n";
                dos.write(fileSize.getBytes());
                dos.write(byteArray);
                dos.flush();

                Log.v(TAG, "Screenshot sent successfully");
            }
        } catch (IOException e) {
            Log.e(TAG, "Server offline");
        }
    }

    public void sendXML(String xml) {
        try {
            if (socket != null) {
                dos.writeByte('X');
                int size = xml.getBytes("UTF-8").length;
                String fileSize = size + "\n";
                dos.write(fileSize.getBytes());
                dos.write(xml.getBytes(StandardCharsets.UTF_8));
                dos.flush();

                Log.v(TAG, "XML sent successfully");
            }
        } catch (IOException e) {
            Log.e(TAG, "Server offline");
        }
    }

    public void receiveMessages(OnMessageReceived onMessageReceived) {
        new Thread(() -> {
            try {
                BufferedReader reader = new BufferedReader(new InputStreamReader(socket.getInputStream()));
                String message;
                while ((message = reader.readLine()) != null) {
                    onMessageReceived.onReceived(message);
                }
            } catch (IOException e) {
                e.printStackTrace();
            }
        }).start();
    }

    public interface OnMessageReceived {
        void onReceived(String message);
    }
}
