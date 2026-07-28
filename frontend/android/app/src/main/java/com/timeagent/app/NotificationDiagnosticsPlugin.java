package com.timeagent.app;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.capacitorjs.plugins.localnotifications.NotificationDiagnosticsStore;
import org.json.JSONException;
import org.json.JSONObject;

@CapacitorPlugin(name = "NotificationDiagnostics")
public class NotificationDiagnosticsPlugin extends Plugin {
    @PluginMethod
    public void recordSchedules(PluginCall call) {
        JSArray entries = call.getArray("entries", new JSArray());
        for (int index = 0; index < entries.length(); index += 1) {
            try {
                JSONObject entry = entries.getJSONObject(index);
                NotificationDiagnosticsStore.append(
                    getContext(), "scheduled", entry.optInt("notificationId"),
                    entry.has("scheduledAt") ? entry.optLong("scheduledAt") : null,
                    entry.optString("title", null)
                );
            } catch (JSONException ignored) {}
        }
        call.resolve();
    }

    @PluginMethod
    public void getEntries(PluginCall call) {
        JSObject result = new JSObject();
        result.put("entries", NotificationDiagnosticsStore.read(getContext()));
        call.resolve(result);
    }

    @PluginMethod
    public void clearEntries(PluginCall call) {
        NotificationDiagnosticsStore.clear(getContext());
        call.resolve();
    }
}
