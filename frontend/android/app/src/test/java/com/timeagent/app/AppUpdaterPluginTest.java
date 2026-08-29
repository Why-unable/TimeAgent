package com.timeagent.app;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

public class AppUpdaterPluginTest {
    @Test
    public void updateFilenameChangesWithVersionAndDigest() {
        assertEquals(
            "timeagent-update-11-abcdef012345.apk",
            AppUpdaterPlugin.buildUpdateFilename(11L, "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789")
        );
    }
}
