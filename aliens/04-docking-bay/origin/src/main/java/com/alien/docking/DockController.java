package com.alien.docking;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * Pilot-facing docking endpoints. A pilot submits a path for the flight crew to
 * review; the crew reviewer (bot) will fetch it. Open pilot area.
 */
@RestController
public class DockController {

    private final DockQueue queue;

    public DockController(DockQueue queue) {
        this.queue = queue;
    }

    @PostMapping(value = "/dock/notify", produces = MediaType.TEXT_PLAIN_VALUE)
    public String notify(@RequestParam(required = false) String path, HttpServletResponse resp) {
        if (queue.submit(path)) {
            return "QUEUED for crew review: " + path + "\n";
        }
        resp.setStatus(400);
        return "REJECTED: provide a same-origin path (e.g. path=/status)\n";
    }

    /**
     * Open a referenced bay document. The console issues a redirect to the
     * referenced same-origin resource so the viewer loads it in place.
     */
    @GetMapping(value = "/dock/review", produces = MediaType.TEXT_PLAIN_VALUE)
    public String review(@RequestParam(required = false) String doc, HttpServletResponse resp) {
        if (doc == null || !doc.startsWith("/") || doc.startsWith("//")
                || doc.contains("://") || doc.contains("\\")) {
            resp.setStatus(400);
            return "REJECTED: provide a same-origin doc path (e.g. doc=/status)\n";
        }
        resp.setStatus(302);
        resp.setHeader("Location", doc);
        return "";
    }
}
