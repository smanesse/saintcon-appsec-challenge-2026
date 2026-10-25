package com.alien.docking;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * A.L.I.E.N. Ship 04 — Docking Bay origin.
 *
 * The real launch subsystem. The pilot area is open; the launch code is a
 * crew-only secret. This server runs on container-loopback behind the Varnish
 * edge — it is never exposed directly.
 */
@SpringBootApplication
public class DockingApplication {
    public static void main(String[] args) {
        SpringApplication.run(DockingApplication.class, args);
    }
}
