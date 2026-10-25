package com.alien.docking;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Crew-only consoles and diagnostics. Reachable only with a flight-crew
 * session. Several consoles print the launch code to the crew on shift.
 */
@RestController
public class CrewController {

    private final Secrets secrets;
    private final DockQueue queue;

    public CrewController(Secrets secrets, DockQueue queue) {
        this.secrets = secrets;
        this.queue = queue;
    }

    /** Launch panel — the headline launch-code readout. */
    @GetMapping(value = "/crew/launch-code", produces = MediaType.TEXT_PLAIN_VALUE)
    public String launchCode() {
        return "LAUNCH-CODE: " + secrets.launchCode + "\n"
                + "(arm, then turn both keys simultaneously)\n";
    }

    /** Ignition keyring console. */
    @GetMapping(value = "/crew/keyring", produces = MediaType.TEXT_PLAIN_VALUE)
    public String keyring() {
        return "IGNITION KEYRING\n"
                + "  primary key : " + secrets.launchCode + "\n"
                + "  backup key  : held by the quartermaster\n";
    }

    /** Manual override console. */
    @GetMapping(value = "/crew/override", produces = MediaType.TEXT_PLAIN_VALUE)
    public String override() {
        return "MANUAL OVERRIDE\n"
                + "  launch authority code: " + secrets.launchCode + "\n";
    }

    /** Pre-launch checklist readout. */
    @GetMapping(value = "/crew/checklist", produces = MediaType.TEXT_PLAIN_VALUE)
    public String checklist() {
        return "PRE-LAUNCH CHECKLIST\n"
                + "  [x] hull sealed\n"
                + "  [x] fuel nominal\n"
                + "  [x] crew aboard\n"
                + "  [x] launch code loaded: " + secrets.launchCode + "\n"
                + "  [ ] two-key turn pending\n";
    }

    /** Telemetry readout, including the current diagnostic code. */
    @GetMapping(value = "/crew/telemetry", produces = MediaType.TEXT_PLAIN_VALUE)
    public String telemetry() {
        return "TELEMETRY: nominal // 14 subsystems green\n"
                + "DIAG-CODE: " + secrets.diagCode + "\n";
    }

    /** Crew reviewer drains its work queue (newline-separated paths). */
    @GetMapping(value = "/crew/pending", produces = MediaType.TEXT_PLAIN_VALUE)
    public String pending() {
        return String.join("\n", queue.drain()) + "\n";
    }
}
