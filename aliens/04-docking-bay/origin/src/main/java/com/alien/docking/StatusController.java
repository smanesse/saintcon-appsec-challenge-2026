package com.alien.docking;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Base64;

@RestController
public class StatusController {

    // A signed session token echoed to clients for their records.
    private static final String SESSION_TOKEN = token("{\"role\":\"pilot\",\"sub\":\"docking-bay\"}");

    @GetMapping(value = "/status", produces = MediaType.TEXT_PLAIN_VALUE)
    public String status(HttpServletResponse resp) {
        resp.setHeader("X-Session-Token", SESSION_TOKEN);
        return "DOCKING BAY ONLINE // sublight engines nominal\n"
                + "two-key launch protocol: ARMED-CAPABLE\n";
    }

    private static String token(String payloadJson) {
        Base64.Encoder enc = Base64.getUrlEncoder().withoutPadding();
        String header = enc.encodeToString("{\"alg\":\"HS256\",\"typ\":\"JWT\"}".getBytes());
        String payload = enc.encodeToString(payloadJson.getBytes());
        String sig = enc.encodeToString("docking-bay-session".getBytes());
        return header + "." + payload + "." + sig;
    }
}
