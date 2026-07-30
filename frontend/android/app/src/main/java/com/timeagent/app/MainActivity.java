package com.timeagent.app;

import android.os.Bundle;
import android.graphics.Color;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsControllerCompat;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(NotificationDiagnosticsPlugin.class);
        super.onCreate(savedInstanceState);
        // Match the installed app's light mobile surface, avoiding a visible
        // seam above or below the WebView.
        getWindow().setStatusBarColor(Color.rgb(244, 247, 251));
        getWindow().setNavigationBarColor(Color.rgb(244, 247, 251));
        WindowCompat.setDecorFitsSystemWindows(getWindow(), true);
        WindowInsetsControllerCompat controller = new WindowInsetsControllerCompat(
            getWindow(), getWindow().getDecorView()
        );
        controller.setAppearanceLightStatusBars(true);
        controller.setAppearanceLightNavigationBars(true);
    }
}
