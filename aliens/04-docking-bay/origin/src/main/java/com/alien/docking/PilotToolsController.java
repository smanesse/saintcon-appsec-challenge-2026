package com.alien.docking;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Base64;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Assorted pilot-facing docking utilities.
 */
@RestController
public class PilotToolsController {

    private static final Map<String, String> BERTHS = Map.of(
            "A1", "occupied: freighter Kestrel",
            "A2", "free",
            "B7", "reserved: crew shuttle");

    private static final Pattern ROLE = Pattern.compile("\"role\"\\s*:\\s*\"([^\"]+)\"");

    /** Look up the status of a numbered berth. */
    @GetMapping(value = "/dock/berth", produces = MediaType.TEXT_PLAIN_VALUE)
    public String berth(@RequestParam(required = false) String id, HttpServletResponse resp) {
        if (id == null) {
            resp.setStatus(400);
            return "specify a berth id, e.g. id=A1\n";
        }
        if (id.matches(".*[\"'`;].*")) {
            resp.setStatus(500);
            return "ERROR: SQL syntax error near '" + id + "' in berth lookup query\n";
        }
        String status = BERTHS.get(id.toUpperCase());
        return status == null ? "no such berth: " + id + "\n" : "berth " + id.toUpperCase() + ": " + status + "\n";
    }

    /** Generate an approach-clearance greeting. */
    @GetMapping(value = "/dock/greet", produces = MediaType.TEXT_PLAIN_VALUE)
    public String greet(@RequestParam(required = false, defaultValue = "pilot") String callsign) {
        return "Approach vector cleared for " + callsign + ". Hold at the outer marker.\n";
    }

    /** Report the caller's role, as read from their session token. */
    @GetMapping(value = "/dock/whoami", produces = MediaType.TEXT_PLAIN_VALUE)
    public String whoami(@RequestHeader(value = "X-Session-Token", required = false) String token) {
        String role = "pilot";
        if (token != null) {
            try {
                String[] parts = token.split("\\.");
                if (parts.length >= 2) {
                    String payload = new String(Base64.getUrlDecoder().decode(parts[1]));
                    Matcher m = ROLE.matcher(payload);
                    if (m.find()) {
                        role = m.group(1);
                    }
                }
            } catch (RuntimeException ignored) {
                // malformed token — fall back to the default role
            }
        }
        return "session role: " + role + "\n";
    }
}
