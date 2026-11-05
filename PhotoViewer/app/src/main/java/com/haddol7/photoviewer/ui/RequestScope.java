package com.haddol7.photoviewer.ui;

/** Late worker results must not overwrite a different server or screen. */
public final class RequestScope {
    private long generation;
    private boolean closed;
    public synchronized long current() { return generation; }
    public synchronized long advance() { return ++generation; }
    public synchronized boolean accepts(long ticket) { return !closed && ticket == generation; }
    public synchronized void close() { closed = true; generation++; }
}
