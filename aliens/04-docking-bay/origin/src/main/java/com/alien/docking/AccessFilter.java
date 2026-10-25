package com.alien.docking;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * Crew area (/crew/*) requires a crew session. The pilot area (/status,
 * /dock/*, /launch/*) is open — this ship stands alone.
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class AccessFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(HttpServletRequest req, HttpServletResponse resp, FilterChain chain)
            throws ServletException, IOException {
        String path = req.getServletPath();

        boolean crewArea = path.startsWith("/crew/");

        if (crewArea) {
            HttpSession s = req.getSession(false);
            Object role = (s == null) ? null : s.getAttribute("role");
            if (!"crew".equals(role)) {
                deny(resp, "CREW ONLY: this diagnostic requires a flight-crew session.");
                return;
            }
        }

        chain.doFilter(req, resp);
    }

    private static void deny(HttpServletResponse resp, String msg) throws IOException {
        resp.setStatus(403);
        resp.setContentType("text/plain");
        resp.getWriter().write(msg + "\n");
    }
}
