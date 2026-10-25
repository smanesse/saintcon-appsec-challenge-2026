package com.alien.docking;

import org.springframework.stereotype.Component;

import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;

/**
 * Pilot-submitted docking requests awaiting crew review. A pilot POSTs a path
 * to /dock/notify; the flight crew (the in-container bot) drains this queue and
 * fetches each path. Only same-origin paths are accepted, and the crew area is
 * off-limits — a pilot cannot send the reviewer straight to a crew console.
 */
@Component
public class DockQueue {
    private final ConcurrentLinkedQueue<String> pending = new ConcurrentLinkedQueue<>();

    /** Accept only a same-origin absolute path (no scheme/host), and never a
     *  crew path, so the reviewer can't be aimed at a crew-only console. */
    public boolean submit(String path) {
        if (path == null) return false;
        path = path.trim();
        if (!path.startsWith("/") || path.startsWith("//")) return false;
        if (path.contains("://") || path.contains("\\")) return false;
        if (resolvesToCrew(path)) return false;
        pending.add(path);
        return true;
    }

    private static boolean resolvesToCrew(String path) {
        String probe = path;
        try {
            probe = URLDecoder.decode(path, StandardCharsets.UTF_8);
        } catch (IllegalArgumentException ignored) {
            // malformed %-escape: fall back to the raw form
        }
        String pathOnly = probe.split("\\?", 2)[0].replace("/./", "/");
        String lower = pathOnly.toLowerCase();
        return lower.equals("/crew") || lower.startsWith("/crew/");
    }

    /** Crew drains the queue (returns and clears). */
    public List<String> drain() {
        List<String> out = new ArrayList<>();
        for (String p; (p = pending.poll()) != null; ) out.add(p);
        return out;
    }
}
