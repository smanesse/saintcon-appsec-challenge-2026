package com.alien.docking;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Two-key launch. Arming issues one launch credit. Firing is the two-key
 * protocol: a single key alone cannot launch — it waits for a second key to be
 * turned simultaneously, and only a confirmed pair of keys proceeds to launch.
 */
@RestController
public class LaunchController {

    private final Secrets secrets;

    private final AtomicInteger credits = new AtomicInteger(0);
    private final AtomicInteger launches = new AtomicInteger(0);
    private volatile CyclicBarrier keyRendezvous = new CyclicBarrier(2);

    public LaunchController(Secrets secrets) {
        this.secrets = secrets;
    }

    @GetMapping(value = "/launch/arm", produces = MediaType.TEXT_PLAIN_VALUE)
    public String arm(@RequestParam(required = false) String code, HttpServletResponse resp) {
        if (!secrets.launchCode.equals(code)) {
            resp.setStatus(403);
            return "DENIED: invalid launch code\n";
        }
        synchronized (this) {
            credits.set(1);
            launches.set(0);
            keyRendezvous = new CyclicBarrier(2);
        }
        return "ARMED. One launch credit issued.\n"
                + "Two-key protocol: both pilots must turn their key SIMULTANEOUSLY.\n";
    }

    @GetMapping(value = "/launch/fire", produces = MediaType.TEXT_PLAIN_VALUE)
    public String fire(@RequestParam(required = false) String code, HttpServletResponse resp) {
        if (!secrets.launchCode.equals(code)) {
            resp.setStatus(403);
            return "DENIED: invalid launch code\n";
        }

        if (credits.get() <= 0) {
            resp.setStatus(403);
            return "DENIED: no launch credits (arm first)\n";
        }

        // Hold this key and wait for a partner key to be turned at the same time.
        CyclicBarrier barrier = keyRendezvous;
        try {
            barrier.await(300, TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            return "SINGLE KEY held — no simultaneous second key. Launch aborted.\n";
        } catch (BrokenBarrierException | InterruptedException e) {
            return "KEY sync broken — retry the simultaneous turn.\n";
        }

        // A confirmed pair of keys — proceed with the launch.
        credits.decrementAndGet();
        int n = launches.incrementAndGet();

        if (n >= 2) {
            return "SIMULTANEOUS LAUNCH CONFIRMED. Mothership away!\n\nFLAG: " + secrets.flag + "\n";
        }
        return "Launch key " + n + " confirmed — awaiting the simultaneous partner key...\n";
    }
}
