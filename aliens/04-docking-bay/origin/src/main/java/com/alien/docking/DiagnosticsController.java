package com.alien.docking;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Operations/diagnostics surface.
 */
@RestController
public class DiagnosticsController {

    @GetMapping(value = "/actuator", produces = MediaType.APPLICATION_JSON_VALUE)
    public String index() {
        return "{\"_links\":{"
                + "\"self\":{\"href\":\"/actuator\"},"
                + "\"health\":{\"href\":\"/actuator/health\"},"
                + "\"info\":{\"href\":\"/actuator/info\"},"
                + "\"env\":{\"href\":\"/actuator/env\"},"
                + "\"metrics\":{\"href\":\"/actuator/metrics\"},"
                + "\"mappings\":{\"href\":\"/actuator/mappings\"},"
                + "\"heapdump\":{\"href\":\"/actuator/heapdump\"}"
                + "}}";
    }

    @GetMapping(value = "/actuator/health", produces = MediaType.APPLICATION_JSON_VALUE)
    public String health() {
        return "{\"status\":\"UP\"}";
    }

    @GetMapping(value = "/actuator/info", produces = MediaType.APPLICATION_JSON_VALUE)
    public String info() {
        return "{\"app\":\"docking-bay\",\"group\":\"alien.flight-systems\"}";
    }

    @GetMapping(value = {
            "/actuator/env", "/actuator/env/**",
            "/actuator/metrics", "/actuator/metrics/**",
            "/actuator/mappings", "/actuator/beans",
            "/actuator/configprops", "/actuator/threaddump",
            "/actuator/heapdump", "/actuator/loggers"},
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> restricted() {
        return ResponseEntity.status(401)
                .body("{\"error\":\"this management endpoint requires operator credentials\"}");
    }
}
