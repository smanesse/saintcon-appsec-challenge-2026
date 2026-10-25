package com.alien.docking;

import java.io.Serializable;

/** A docking manifest snapshot, as persisted by the backup/restore tooling. */
public class ManifestBackup implements Serializable {
    private static final long serialVersionUID = 1L;

    public String name;
    public String berth;
    public int priority;

    @Override
    public String toString() {
        return "ManifestBackup{name=" + name + ", berth=" + berth + ", priority=" + priority + "}";
    }
}
