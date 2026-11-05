package com.haddol7.photoviewer.ui;

import org.junit.Test;
import static org.junit.Assert.*;

public class RequestScopeTest {
    @Test public void currentScreenAcceptsItsResult() {
        RequestScope scope = new RequestScope(); assertTrue(scope.accepts(scope.current()));
    }
    @Test public void changingScreenOrOriginRejectsLateResults() {
        RequestScope scope = new RequestScope(); long old = scope.current();
        long next = scope.advance(); assertFalse(scope.accepts(old)); assertTrue(scope.accepts(next));
    }
    @Test public void destroyRejectsEvenTheLatestTicket() {
        RequestScope scope = new RequestScope(); long ticket = scope.advance();
        scope.close(); assertFalse(scope.accepts(ticket)); assertFalse(scope.accepts(scope.current()));
    }
}
