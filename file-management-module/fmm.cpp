
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <fstream>
#include <sstream>
#include <map>
#include <dirent.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <cctype>
#include <thread>
#include <regex>
#include <ctime>
#include <climits>
#include <cerrno>

#define PORT 2121
#define CREDS_FILE "credentials.txt"
#define ROOT_DIR "./ftproot"

#define SECRET_DIR "./secret"
#define SECRET_FLAG_FILE "./secret/flag.txt"
#define DEFAULT_FLAG "FLAG{local-dev-default}"

// An authenticated-only credential, materialized inside the served root so a
// logged-in session can retrieve it with an ordinary RETR.
#define VAULT_DIR "./ftproot/vault"
#define VAULT_FLAG_FILE "./ftproot/vault/manifest.dat"

struct Session {
    char username[32];
    bool authenticated;
    std::string cwd;

    bool binary_mode;
    int pasv_listen_fd;
    sockaddr_in port_addr;
    bool port_active;

    Session()
        : authenticated(false), cwd(ROOT_DIR),
          binary_mode(true), pasv_listen_fd(-1), port_active(false) {
        memset(username, 0, sizeof(username));
        memset(&port_addr, 0, sizeof(port_addr));
    }

    ~Session() {
        if (pasv_listen_fd >= 0) close(pasv_listen_fd);
    }
};

bool check_credentials(const std::string& username, const std::string& password) {
    std::ifstream f(CREDS_FILE);
    if (!f.is_open()) {
        fprintf(stderr, "[!] Could not open credentials file: %s\n", CREDS_FILE);
        return false;
    }

    std::string line;
    while (std::getline(f, line)) {
        if (line.empty() || line[0] == '#') continue;
        size_t sep = line.find(':');
        if (sep == std::string::npos) continue;

        std::string user = line.substr(0, sep);
        std::string pass = line.substr(sep + 1);

        if (user == username && pass == password) {
            return true;
        }
    }
    return false;
}

void write_flag_files() {
    const char* env = getenv("FMM_FLAG");
    std::string flag = (env && env[0] != '\0') ? env : DEFAULT_FLAG;

    if (mkdir(SECRET_DIR, 0755) != 0 && errno != EEXIST) {
        fprintf(stderr, "[!] Warning: could not create %s\n", SECRET_DIR);
    }

    std::ofstream flag_file(SECRET_FLAG_FILE, std::ios::trunc);
    if (flag_file.is_open()) {
        flag_file << flag << "\n";
    } else {
        fprintf(stderr, "[!] Warning: could not write %s\n", SECRET_FLAG_FILE);
    }

    std::string marker_path = std::string(SECRET_DIR) + "/" + flag;
    std::ofstream marker_file(marker_path, std::ios::trunc);
    if (marker_file.is_open()) {
        marker_file << flag << "\n";
    } else {
        fprintf(stderr, "[!] Warning: could not write %s\n", marker_path.c_str());
    }

    // A copy inside the served root, as file CONTENT, so a session that has
    // authenticated can fetch it with a normal RETR (RETR's containment check
    // allows within-root reads).
    if (mkdir(VAULT_DIR, 0755) != 0 && errno != EEXIST) {
        fprintf(stderr, "[!] Warning: could not create %s\n", VAULT_DIR);
    }
    std::ofstream vault_file(VAULT_FLAG_FILE, std::ios::trunc);
    if (vault_file.is_open()) {
        vault_file << flag << "\n";
    } else {
        fprintf(stderr, "[!] Warning: could not write %s\n", VAULT_FLAG_FILE);
    }
}

static std::map<std::string, Session*> g_sessions;

std::string generate_token() {
    int n = rand() % 100000;
    char buf[16];
    snprintf(buf, sizeof(buf), "%05d", n);
    return std::string(buf);
}

void send_line(int fd, const std::string& msg) {
    std::string out = msg + "\r\n";
    send(fd, out.c_str(), out.size(), 0);
}

std::string recv_line(int fd) {
    std::string line;
    char c;
    while (true) {
        ssize_t n = recv(fd, &c, 1, 0);
        if (n <= 0) return line;
        if (c == '\n') break;
        if (c != '\r') line += c;
    }
    return line;
}

std::pair<std::string, std::string> parse_command(const std::string& raw) {
    size_t pos = raw.find(' ');
    if (pos == std::string::npos) return {raw, ""};
    return {raw.substr(0, pos), raw.substr(pos + 1)};
}


static int g_next_data_port = PORT + 1;

int open_data_connection(Session* session) {
    if (session->pasv_listen_fd >= 0) {
        sockaddr_in peer{};
        socklen_t plen = sizeof(peer);
        int data_fd = accept(session->pasv_listen_fd, (sockaddr*)&peer, &plen);
        close(session->pasv_listen_fd);
        session->pasv_listen_fd = -1;
        return data_fd;
    }
    if (session->port_active) {
        int data_fd = socket(AF_INET, SOCK_STREAM, 0);
        session->port_active = false;
        if (data_fd < 0) return -1;
        if (connect(data_fd, (sockaddr*)&session->port_addr,
                    sizeof(session->port_addr)) < 0) {
            close(data_fd);
            return -1;
        }
        return data_fd;
    }
    return -1;
}

void handle_type(Session* session, int fd, const std::string& arg) {
    if (!session->authenticated) { send_line(fd, "530 Please login first"); return; }
    if (arg.empty()) { send_line(fd, "501 Syntax error in parameters"); return; }
    char t = toupper((unsigned char)arg[0]);
    if (t == 'I') {
        session->binary_mode = true;
        send_line(fd, "200 Type set to I");
    } else if (t == 'A') {
        session->binary_mode = false;
        send_line(fd, "200 Type set to A");
    } else {
        send_line(fd, "504 Command not implemented for that parameter");
    }
}

void handle_pasv(Session* session, int fd) {
    if (!session->authenticated) { send_line(fd, "530 Please login first"); return; }

    int lfd = socket(AF_INET, SOCK_STREAM, 0);
    if (lfd < 0) { send_line(fd, "425 Can't open data connection"); return; }
    int opt = 1;
    setsockopt(lfd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    int data_port = g_next_data_port++;
    sockaddr_in daddr{};
    daddr.sin_family = AF_INET;
    daddr.sin_addr.s_addr = INADDR_ANY;
    daddr.sin_port = htons(data_port);
    if (bind(lfd, (sockaddr*)&daddr, sizeof(daddr)) < 0 || listen(lfd, 1) < 0) {
        close(lfd);
        send_line(fd, "425 Can't open data connection");
        return;
    }

    if (session->pasv_listen_fd >= 0) close(session->pasv_listen_fd);
    session->pasv_listen_fd = lfd;
    session->port_active = false;

    sockaddr_in local{};
    socklen_t local_len = sizeof(local);
    unsigned char h1 = 127, h2 = 0, h3 = 0, h4 = 1;
    if (getsockname(fd, (sockaddr*)&local, &local_len) == 0) {
        unsigned char* b = (unsigned char*)&local.sin_addr.s_addr;
        h1 = b[0]; h2 = b[1]; h3 = b[2]; h4 = b[3];
    }

    int p1 = (data_port >> 8) & 0xff;
    int p2 = data_port & 0xff;
    char reply[80];
    snprintf(reply, sizeof(reply),
             "227 Entering Passive Mode (%d,%d,%d,%d,%d,%d)", h1, h2, h3, h4, p1, p2);
    send_line(fd, reply);
}

void handle_port(Session* session, int fd, const std::string& arg) {
    if (!session->authenticated) { send_line(fd, "530 Please login first"); return; }

    int h1, h2, h3, h4, p1, p2;
    if (sscanf(arg.c_str(), "%d,%d,%d,%d,%d,%d", &h1, &h2, &h3, &h4, &p1, &p2) != 6) {
        send_line(fd, "501 Syntax error in parameters");
        return;
    }

    sockaddr_in target{};
    target.sin_family = AF_INET;
    target.sin_port = htons((p1 << 8) | p2);
    char ip[16];
    snprintf(ip, sizeof(ip), "%d.%d.%d.%d", h1, h2, h3, h4);
    target.sin_addr.s_addr = inet_addr(ip);

    if (session->pasv_listen_fd >= 0) {
        close(session->pasv_listen_fd);
        session->pasv_listen_fd = -1;
    }
    session->port_addr = target;
    session->port_active = true;
    send_line(fd, "200 PORT command successful");
}


void handle_user(Session* session, int fd, const std::string& arg) {
    strcpy(session->username, arg.c_str());
    send_line(fd, "331 Password required for " + arg);
}

void handle_pass(Session* session, int fd, const std::string& arg) {
    std::string user(session->username);
    if (check_credentials(user, arg)) {
        session->authenticated = true;
        std::string token = generate_token();
        g_sessions[token] = session;
        send_line(fd, "230 Login successful token=" + token);
    } else {
        send_line(fd, "530 Login incorrect");
    }
}

void handle_sess(Session* session, int fd, const std::string& arg) {
    auto it = g_sessions.find(arg);
    if (it == g_sessions.end()) {
        send_line(fd, "530 Unknown or expired session token");
        return;
    }
    Session* target = it->second;
    session->authenticated = true;
    strcpy(session->username, target->username);
    send_line(fd, "230 Session resumed as " + std::string(target->username));
}

void handle_list(Session* session, int fd) {
    if (!session->authenticated) { send_line(fd, "530 Please login first"); return; }
    std::ostringstream out;
    DIR* d = opendir(session->cwd.c_str());
    if (!d) { send_line(fd, "450 Could not open directory"); return; }
    struct dirent* entry;
    while ((entry = readdir(d)) != nullptr) {
        out << entry->d_name << "\r\n";
    }
    closedir(d);

    int data_fd = open_data_connection(session);
    if (data_fd < 0) { send_line(fd, "425 Use PASV or PORT first"); return; }

    send_line(fd, "150 Here comes the directory listing");
    std::string body = out.str();
    send(data_fd, body.c_str(), body.size(), 0);
    close(data_fd);
    send_line(fd, "226 Directory send OK");
}

void log_download(const std::string& filename) {
    std::string cmd = "echo \"Download requested: " + filename + "\" >> transfer.log";
    system(cmd.c_str());
}

bool is_path_within_root(const std::string& path) {
    char resolved[PATH_MAX];
    if (!realpath(path.c_str(), resolved)) return false;

    char root[PATH_MAX];
    if (!realpath(ROOT_DIR, root)) return false;

    std::string resolved_str(resolved);
    std::string root_str(root);
    return resolved_str.compare(0, root_str.size(), root_str) == 0;
}

bool is_valid_filename(const std::string& name) {
    static const std::regex pattern(R"(^([a-zA-Z0-9_]+)+\.[a-zA-Z0-9]+$)");
    return std::regex_match(name, pattern);
}

void handle_retr(Session* session, int fd, const std::string& arg) {
    if (!session->authenticated) { send_line(fd, "530 Please login first"); return; }
    if (arg.empty()) { send_line(fd, "501 Syntax error in parameters"); return; }

    log_download(arg);

    std::string path = session->cwd + "/" + arg;

    if (!is_path_within_root(path)) {
        send_line(fd, "550 Access denied");
        return;
    }

    usleep(200 * 1000);

    std::ifstream f(path, std::ios::binary);
    if (!f.is_open()) { send_line(fd, "550 File not found"); return; }

    int data_fd = open_data_connection(session);
    if (data_fd < 0) { send_line(fd, "425 Use PASV or PORT first"); return; }

    send_line(fd, "150 Opening data connection");
    char buf[4096];
    while (f.read(buf, sizeof(buf)) || f.gcount() > 0) {
        send(data_fd, buf, f.gcount(), 0);
    }
    close(data_fd);
    send_line(fd, "226 Transfer complete");
}

void handle_stor(Session* session, int fd, const std::string& arg) {
    if (!session->authenticated) { send_line(fd, "530 Please login first"); return; }
    if (arg.empty()) { send_line(fd, "501 Syntax error in parameters"); return; }

    if (!is_valid_filename(arg)) {
        send_line(fd, "553 Invalid filename");
        return;
    }

    std::string path = session->cwd + "/" + arg;
    std::ofstream f(path, std::ios::binary | std::ios::trunc);
    if (!f.is_open()) { send_line(fd, "550 Could not create file"); return; }

    int data_fd = open_data_connection(session);
    if (data_fd < 0) { send_line(fd, "425 Use PASV or PORT first"); return; }

    send_line(fd, "150 Ok to send data");
    char buf[4096];
    ssize_t n;
    while ((n = recv(data_fd, buf, sizeof(buf), 0)) > 0) {
        f.write(buf, n);
    }
    close(data_fd);
    send_line(fd, "226 Transfer complete");
}

void handle_cwd(Session* session, int fd, const std::string& arg) {
    if (!session->authenticated) { send_line(fd, "530 Please login first"); return; }
    if (arg.empty()) { send_line(fd, "501 Syntax error in parameters"); return; }

    std::string new_path = session->cwd + "/" + arg;

    DIR* d = opendir(new_path.c_str());
    if (!d) {
        send_line(fd, "550 Failed to change directory");
        return;
    }
    closedir(d);

    session->cwd = new_path;
    send_line(fd, "250 Directory successfully changed");
}

void handle_pwd(Session* session, int fd) {
    send_line(fd, "257 \"" + session->cwd + "\"");
}

void handle_client(int fd) {
    Session* session = new Session();
    send_line(fd, "220 Welcome to FMM (educational build)");

    bool freed = false;

    while (true) {
        std::string raw = recv_line(fd);
        if (raw.empty()) break;

        auto parsed = parse_command(raw);
        std::string cmd = parsed.first;
        std::string arg = parsed.second;
        for (auto& c : cmd) c = toupper((unsigned char)c);

        if (cmd == "USER") {
            handle_user(session, fd, arg);
        } else if (cmd == "PASS") {
            handle_pass(session, fd, arg);
        } else if (cmd == "TYPE") {
            handle_type(session, fd, arg);
        } else if (cmd == "PASV") {
            handle_pasv(session, fd);
        } else if (cmd == "PORT") {
            handle_port(session, fd, arg);
        } else if (cmd == "LIST") {
            handle_list(session, fd);
        } else if (cmd == "RETR") {
            handle_retr(session, fd, arg);
        } else if (cmd == "STOR") {
            handle_stor(session, fd, arg);
        } else if (cmd == "PWD") {
            handle_pwd(session, fd);
        } else if (cmd == "CWD") {
            handle_cwd(session, fd, arg);
        } else if (cmd == "SESS") {
            handle_sess(session, fd, arg);
        } else if (cmd == "QUIT") {
            send_line(fd, "221 Goodbye");
            delete session;
            freed = true;
        } else {
            send_line(fd, "502 Command not implemented");
        }

        fprintf(stderr, "[debug] last command from user='%s' authenticated=%d\n",
                session->username, session->authenticated);

        if (freed) break;
    }

    if (!freed) delete session;
    close(fd);
}

int main() {
    srand((unsigned)time(nullptr));

    write_flag_files();

    std::ifstream creds_check(CREDS_FILE);
    if (!creds_check.is_open()) {
        fprintf(stderr, "[!] Warning: could not open %s - all logins will fail.\n", CREDS_FILE);
    }

    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(PORT);

    if (bind(server_fd, (sockaddr*)&addr, sizeof(addr)) < 0) {
        perror("bind");
        return 1;
    }
    if (listen(server_fd, 16) < 0) {
        perror("listen");
        return 1;
    }

    printf("[*] FMM listening on port %d\n", PORT);

    while (true) {
        sockaddr_in client_addr{};
        socklen_t len = sizeof(client_addr);
        int client_fd = accept(server_fd, (sockaddr*)&client_addr, &len);
        if (client_fd < 0) continue;

        std::thread(handle_client, client_fd).detach();
    }

    return 0;
}
