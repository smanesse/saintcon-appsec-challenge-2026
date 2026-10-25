package com.alien.docking;

import java.io.IOException;
import java.io.InputStream;
import java.io.InvalidClassException;
import java.io.ObjectInputStream;
import java.io.ObjectStreamClass;
import java.util.Set;

/**
 * ObjectInputStream restricted to the manifest backup data model, so restoring
 * a snapshot cannot instantiate arbitrary types from the stream.
 */
class SafeObjectInputStream extends ObjectInputStream {

    private static final Set<String> ALLOWED = Set.of(
            "com.alien.docking.ManifestBackup",
            "java.lang.String",
            "java.lang.Number",
            "java.lang.Integer",
            "java.lang.Long",
            "java.lang.Boolean",
            "java.util.HashMap",
            "java.util.LinkedHashMap",
            "java.util.ArrayList",
            "[Ljava.lang.Object;");

    SafeObjectInputStream(InputStream in) throws IOException {
        super(in);
    }

    @Override
    protected Class<?> resolveClass(ObjectStreamClass desc) throws IOException, ClassNotFoundException {
        if (!ALLOWED.contains(desc.getName())) {
            throw new InvalidClassException(desc.getName(), "class not permitted in a manifest backup");
        }
        return super.resolveClass(desc);
    }
}
