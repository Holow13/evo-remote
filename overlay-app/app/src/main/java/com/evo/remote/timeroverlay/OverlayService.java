package com.evo.remote.timeroverlay;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.graphics.PixelFormat;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.provider.Settings;
import android.view.Gravity;
import android.view.LayoutInflater;
import android.view.View;
import android.view.WindowManager;
import android.widget.TextView;

public class OverlayService extends Service {
    public static final String ACTION_UPDATE = "com.evo.remote.TIMER_UPDATE";
    public static final String ACTION_HIDE = "com.evo.remote.TIMER_HIDE";

    private static OverlayService instance;

    private WindowManager windowManager;
    private View overlayView;
    private TextView timeView;
    private TextView labelView;
    private final Handler handler = new Handler(Looper.getMainLooper());

    private String state = "idle";
    private String label = "";
    private long endAtMs = 0L;
    private int pausedLeft = 0;

    private final Runnable tickRunnable = new Runnable() {
        @Override
        public void run() {
            render();
            if ("running".equals(state)) {
                handler.postDelayed(this, 250L);
            }
        }
    };

    @Override
    public void onCreate() {
        super.onCreate();
        instance = this;
        windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
        startAsForeground();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && intent.getAction() != null) {
            if (ACTION_HIDE.equals(intent.getAction())) {
                removeOverlay();
                stopSelf();
                return START_NOT_STICKY;
            }
            if (ACTION_UPDATE.equals(intent.getAction())) {
                applyExtras(intent);
            }
        }
        if (!Settings.canDrawOverlays(this)) {
            stopSelf();
            return START_NOT_STICKY;
        }
        ensureOverlay();
        handler.removeCallbacks(tickRunnable);
        handler.post(tickRunnable);
        return START_STICKY;
    }

    private void applyExtras(Intent intent) {
        if (intent.hasExtra("state")) {
            state = intent.getStringExtra("state");
        }
        if (intent.hasExtra("label")) {
            label = intent.getStringExtra("label");
        }
        endAtMs = intent.getLongExtra("endAt", 0L);
        pausedLeft = intent.getIntExtra("pausedLeft", 0);
    }

    private void ensureOverlay() {
        if (overlayView != null) {
            return;
        }
        LayoutInflater inflater = LayoutInflater.from(this);
        overlayView = inflater.inflate(R.layout.overlay_timer, null);
        timeView = overlayView.findViewById(R.id.overlay_time);
        labelView = overlayView.findViewById(R.id.overlay_label);

        int overlayType = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                : WindowManager.LayoutParams.TYPE_PHONE;

        WindowManager.LayoutParams params = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                overlayType,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                        | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                PixelFormat.TRANSLUCENT);
        params.gravity = Gravity.TOP | Gravity.END;
        params.x = 24;
        params.y = 24;
        windowManager.addView(overlayView, params);
    }

    private void render() {
        if (timeView == null || labelView == null) {
            return;
        }
        labelView.setText(label == null || label.isEmpty() ? "Сессия" : label);

        if ("finished".equals(state)) {
            timeView.setText("00:00");
            timeView.setTextColor(0xFFFF5252);
            return;
        }
        if ("idle".equals(state)) {
            timeView.setText("—:—");
            timeView.setTextColor(0xFF6A6A82);
            return;
        }

        int left;
        if ("paused".equals(state)) {
            left = pausedLeft;
            timeView.setTextColor(0xFFF0B429);
        } else {
            left = Math.max(0, (int) ((endAtMs - System.currentTimeMillis()) / 1000L));
            timeView.setTextColor(left <= 300 ? 0xFFFF5252 : 0xFF3DDC84);
        }
        timeView.setText(format(left));
    }

    private static String format(int sec) {
        int s = Math.max(0, sec);
        int h = s / 3600;
        int m = (s % 3600) / 60;
        int r = s % 60;
        if (h > 0) {
            return String.format("%02d:%02d:%02d", h, m, r);
        }
        return String.format("%02d:%02d", m, r);
    }

    private void removeOverlay() {
        handler.removeCallbacks(tickRunnable);
        if (overlayView != null && windowManager != null) {
            try {
                windowManager.removeView(overlayView);
            } catch (Exception ignored) {
            }
            overlayView = null;
            timeView = null;
            labelView = null;
        }
    }

    private void startAsForeground() {
        String channelId = "evo_timer_overlay";
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    channelId, "Club Timer", NotificationManager.IMPORTANCE_MIN);
            channel.setShowBadge(false);
            nm.createNotificationChannel(channel);
        }
        Notification notification = new Notification.Builder(this, channelId)
                .setContentTitle("Клуб · таймер")
                .setContentText("Оверлей активен")
                .setSmallIcon(android.R.drawable.ic_menu_recent_history)
                .setOngoing(true)
                .build();
        startForeground(1, notification);
    }

    public static void hide(Context context) {
        Intent intent = new Intent(context, OverlayService.class);
        intent.setAction(ACTION_HIDE);
        context.startService(intent);
    }

    @Override
    public void onDestroy() {
        removeOverlay();
        instance = null;
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
