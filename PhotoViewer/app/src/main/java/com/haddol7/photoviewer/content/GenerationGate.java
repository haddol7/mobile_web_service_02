package com.haddol7.photoviewer.content;

/** Results belong to one image/request generation, even when cancellation loses a race. */
public final class GenerationGate {
    private long generation;
    public synchronized long advance() { return ++generation; }
    public synchronized long current() { return generation; }
    public synchronized boolean accepts(long ticket) { return generation==ticket; }
}
