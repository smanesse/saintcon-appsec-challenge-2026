package com.alien.docking;

import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * Crew sign-in. Only the flight crew knows these credentials (minted at boot,
 * injected from env), so the crew reviewer can establish its session.
 */
@RestController
public class AuthController {

    private final Secrets secrets;

    public AuthController(Secrets secrets) {
        this.secrets = secrets;
    }

    @PostMapping(value = "/login", produces = MediaType.TEXT_PLAIN_VALUE)
    public String login(@RequestParam(required = false) String user,
                        @RequestParam(required = false) String pass,
                        HttpSession session,
                        HttpServletResponse resp) {
        if (secrets.crewUser.equals(user) && secrets.crewPass.equals(pass)) {
            session.setAttribute("role", "crew");
            return "WELCOME, FLIGHT CREW.\n";
        }
        resp.setStatus(401);
        return "INVALID CREW CREDENTIALS.\n";
    }
}
