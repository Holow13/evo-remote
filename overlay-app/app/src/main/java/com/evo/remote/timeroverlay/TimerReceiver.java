package com.evo.remote.timeroverlay;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public class TimerReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null || intent.getAction() == null) {
            return;
        }
        String action = intent.getAction();
        if ("com.evo.remote.TIMER_HIDE".equals(action)) {
            OverlayService.hide(context);
            return;
        }
        if ("com.evo.remote.TIMER_UPDATE".equals(action)) {
            Intent service = new Intent(context, OverlayService.class);
            service.setAction(action);
            service.putExtras(intent.getExtras());
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
                context.startForegroundService(service);
            } else {
                context.startService(service);
            }
        }
    }
}
