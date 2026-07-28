import type { CapacitorConfig } from "@capacitor/cli";

// The web assets are the Vite build output. When building the APK, set
// VITE_API_BASE_URL to the public backend origin so apiRequest talks to it
// (the WebView itself serves the bundled files from https://localhost).
const config: CapacitorConfig = {
  appId: "com.timeagent.app",
  appName: "Time Agent",
  webDir: "dist",
  server: {
    androidScheme: "https",
  },
  plugins: {
    LocalNotifications: {
      smallIcon: "ic_stat_icon",
      iconColor: "#0f172a",
    },
  },
};

export default config;
