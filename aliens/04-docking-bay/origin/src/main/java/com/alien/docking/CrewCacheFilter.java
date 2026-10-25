package com.alien.docking;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.Set;

/**
 * Marks sensitive crew consoles as non-cacheable, so the edge never retains
 * their live operational readouts.
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class CrewCacheFilter extends OncePerRequestFilter {

    private static final Set<String> NO_STORE = Set.of(
            "/crew/launch-code",
            "/crew/keyring",
            "/crew/override",
            "/crew/pending");

    @Override
    protected void doFilterInternal(HttpServletRequest req, HttpServletResponse resp, FilterChain chain)
            throws ServletException, IOException {
        if (NO_STORE.contains(req.getServletPath())) {
            resp.setHeader("Cache-Control", "private, no-store");
        }
        chain.doFilter(req, resp);
    }
}
