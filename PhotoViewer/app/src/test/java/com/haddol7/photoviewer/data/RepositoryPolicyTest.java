package com.haddol7.photoviewer.data;

import java.io.IOException;
import org.junit.Test;
import static org.junit.Assert.*;

/** URL guards only: real JSON parsing and network behavior require Android tests. */
public class RepositoryPolicyTest {
    @Test public void normalizesRootWithoutSharingCookieManagers() {
        PhotoRepository repository = new PhotoRepository("https://daejinha.pythonanywhere.com");
        assertEquals("https://daejinha.pythonanywhere.com/", repository.getBaseUrl());
        repository.clearSession();
    }
    @Test(expected = IllegalArgumentException.class) public void baseCannotContainCredentials() {
        new PhotoRepository("https://user:password@example.com/");
    }
    @Test(expected = IllegalArgumentException.class) public void baseMustBeHttpOrigin() {
        new PhotoRepository("https://example.com/api/?csrf=token");
    }
    @Test public void imageRequestCannotLeakCookiesToForeignOrigin() throws Exception {
        PhotoRepository repository = new PhotoRepository("https://daejinha.pythonanywhere.com/");
        try { repository.downloadPhoto("https://evil.invalid/photo.png"); fail("Foreign origin must be rejected before network access"); }
        catch (IOException expected) { assertTrue(expected.getMessage().contains("다른 출처")); }
        try { repository.downloadPhoto("http://daejinha.pythonanywhere.com/photo.png"); fail("HTTPS must not downgrade"); }
        catch (IOException expected) { assertTrue(expected.getMessage().contains("다른 출처")); }
    }
    @Test public void diagnosticEndpointCannotBeProductionOrSyncPort() throws Exception {
        PhotoRepository repository = new PhotoRepository("https://daejinha.pythonanywhere.com/");
        for (String endpoint : new String[]{"https://daejinha.pythonanywhere.com/", "http://10.0.2.2:8000/", "http://evil.invalid:8002/"}) {
            try { repository.captureRequest(endpoint); fail("Only local diagnostic port is allowed"); }
            catch (IOException expected) { assertTrue(expected.getMessage().contains("8002")); }
        }
    }
}
