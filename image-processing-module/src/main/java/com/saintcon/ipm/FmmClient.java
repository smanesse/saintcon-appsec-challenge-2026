package com.saintcon.ipm;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Component
public class FmmClient {

    private static final Pattern PASV_REPLY = Pattern.compile(
            "\\((\\d+),(\\d+),(\\d+),(\\d+),(\\d+),(\\d+)\\)");

    @Value("${ipm.fmm.host}")
    private String host;

    @Value("${ipm.fmm.port}")
    private int port;

    @Value("${ipm.fmm.user}")
    private String user;

    @Value("${ipm.fmm.pass}")
    private String pass;

    public void store(String name, byte[] data) throws IOException {
        try (Socket sock = new Socket()) {
            sock.connect(new InetSocketAddress(host, port), 5000);
            sock.setSoTimeout(5000);
            InputStream in = sock.getInputStream();
            OutputStream out = sock.getOutputStream();

            readLine(in);
            login(in, out);

            try (Socket dataSock = openPasvData(in, out)) {
                sendCmd(out, "STOR " + name);
                String ready = readLine(in);
                if (!ready.startsWith("150")) {
                    throw new IOException("FMM STOR rejected: " + ready);
                }

                OutputStream dataOut = dataSock.getOutputStream();
                dataOut.write(data);
                dataOut.flush();
            }

            String done = readLine(in);
            if (!done.startsWith("226")) {
                throw new IOException("FMM STOR did not complete: " + done);
            }
            sendCmd(out, "QUIT");
        }
    }

    public byte[] retrieve(String name) throws IOException {
        try (Socket sock = new Socket()) {
            sock.connect(new InetSocketAddress(host, port), 5000);
            sock.setSoTimeout(5000);
            InputStream in = sock.getInputStream();
            OutputStream out = sock.getOutputStream();

            readLine(in);
            login(in, out);

            byte[] body;
            try (Socket data = openPasvData(in, out)) {
                sendCmd(out, "RETR " + name);
                String first = readLine(in);
                if (!first.startsWith("150")) {
                    throw new IOException("FMM RETR failed: " + first);
                }
                body = IoUtils.readAll(data.getInputStream());
            }

            String done = readLine(in);
            if (!done.startsWith("226")) {
                throw new IOException("FMM RETR did not complete: " + done);
            }
            sendCmd(out, "QUIT");
            return body;
        }
    }


    private void login(InputStream in, OutputStream out) throws IOException {
        sendCmd(out, "USER " + user);
        readLine(in);
        sendCmd(out, "PASS " + pass);
        String reply = readLine(in);
        if (!reply.startsWith("230")) {
            throw new IOException("FMM login failed: " + reply);
        }
    }

    private Socket openPasvData(InputStream in, OutputStream out) throws IOException {
        sendCmd(out, "PASV");
        String reply = readLine(in);
        if (!reply.startsWith("227")) {
            throw new IOException("FMM PASV failed: " + reply);
        }
        Matcher m = PASV_REPLY.matcher(reply);
        if (!m.find()) {
            throw new IOException("FMM PASV reply unparseable: " + reply);
        }
        int p1 = Integer.parseInt(m.group(5));
        int p2 = Integer.parseInt(m.group(6));
        int dataPort = p1 * 256 + p2;

        Socket data = new Socket();
        data.connect(new InetSocketAddress(host, dataPort), 5000);
        data.setSoTimeout(5000);
        return data;
    }


    private void sendCmd(OutputStream out, String line) throws IOException {
        out.write((line + "\n").getBytes(StandardCharsets.UTF_8));
        out.flush();
    }

    private String readLine(InputStream in) throws IOException {
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        int c;
        while ((c = in.read()) != -1) {
            if (c == '\n') break;
            if (c != '\r') buf.write(c);
        }
        return buf.toString(StandardCharsets.UTF_8);
    }

}
