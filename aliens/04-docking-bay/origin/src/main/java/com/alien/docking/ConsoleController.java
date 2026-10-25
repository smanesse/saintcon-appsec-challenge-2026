package com.alien.docking;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ConsoleController {

    @GetMapping(value = "/admin", produces = MediaType.TEXT_PLAIN_VALUE)
    public String admin(HttpServletResponse resp) {
        resp.setStatus(401);
        resp.setHeader("WWW-Authenticate", "Basic realm=\"Docking Ops\"");
        return "operator console requires crew credentials\n";
    }

    /** Redirect to a post-departure destination within the bay console. */
    @GetMapping("/depart")
    public ResponseEntity<String> depart(@RequestParam(required = false) String to) {
        if (to == null) {
            return ResponseEntity.badRequest().body("specify a departure target, e.g. ?to=/status\n");
        }
        if (!to.startsWith("/") || to.startsWith("//")) {
            return ResponseEntity.badRequest().body("external departure vectors are not permitted\n");
        }
        return ResponseEntity.status(302).header("Location", to).body("");
    }
}
