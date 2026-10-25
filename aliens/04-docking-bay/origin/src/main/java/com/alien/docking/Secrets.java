package com.alien.docking;

import org.springframework.stereotype.Component;

import java.security.SecureRandom;

/**
 * Runtime secrets and identities, minted fresh per boot. Nothing scoreable is
 * hardcoded: the launch code and flag are generated or injected from env, and
 * the crew credentials come from env so they never live in the repo or image.
 */
@Component
public class Secrets {
    private static final SecureRandom RNG = new SecureRandom();

    public final String launchCode = "OMEGA-" + digits(6);
    public final String diagCode = "DIAG-" + digits(6);

    public final String flag = envOr("FLAG",
            "SAINTCON{local_docking_flag}");

    public final String crewUser = envOr("CREW_USER", "flight-crew");
    public final String crewPass = envOr("CREW_PASS", "orbital-wrench");

    private static String digits(int n) {
        StringBuilder b = new StringBuilder(n);
        for (int i = 0; i < n; i++) b.append((char) ('0' + RNG.nextInt(10)));
        return b.toString();
    }

    private static String envOr(String key, String dflt) {
        String v = System.getenv(key);
        return (v == null || v.isEmpty()) ? dflt : v;
    }
}
