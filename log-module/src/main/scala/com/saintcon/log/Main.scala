package com.saintcon.log

import cats.effect._
import cats.syntax.all._
import com.comcast.ip4s._
import io.circe.Json
import io.circe.parser.{parse => parseJson}
import org.http4s._
import org.http4s.circe._
import org.http4s.dsl.io._
import org.http4s.headers.`Content-Type`
import org.http4s.ember.server.EmberServerBuilder
import org.http4s.implicits._

import org.apache.logging.log4j.{LogManager, Logger}
import org.apache.logging.log4j.core.LoggerContext

import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Path, Paths}
import java.time.Instant
import scala.jdk.CollectionConverters._

object Config {
  private def env(k: String): Option[String] =
    sys.env.get(k).filter(_.nonEmpty)

  val port: Int =
    env("SERVER_PORT").orElse(env("LOG_PORT")).flatMap(_.toIntOption).getOrElse(8080)

  val logsRoot: Path =
    Paths.get(env("LOG_ROOT").getOrElse("/home/ctf/log/logs")).toAbsolutePath

  val secretPath: Path =
    Paths.get(env("LOG_SECRET").getOrElse("/home/ctf/log/secret/flag.txt")).toAbsolutePath

  val opToken: String = env("LOG_OP_TOKEN").getOrElse("operator-secret")

  val dashboardTail: Int = env("LOG_DASHBOARD_TAIL").flatMap(_.toIntOption).getOrElse(100)
}

object Store {
  private val logger: Logger = LogManager.getLogger("flightrecorder")

  def warmup(): Unit = {
    LogManager.getContext(false).asInstanceOf[LoggerContext].reconfigure()
    var tries = 0
    while (!logger.isInfoEnabled && tries < 250) {
      Thread.sleep(20)
      tries += 1
    }
    logger.info("flight recorder logging initialised")
  }

  def sanitizeSource(s: String): String = {
    val cleaned = s.filter(c => c.isLetterOrDigit || c == '_' || c == '-' || c == '.')
    if (cleaned.isEmpty || cleaned == "." || cleaned == "..") "misc" else cleaned
  }

  private def fileFor(source: String): Path =
    Config.logsRoot.resolve(sanitizeSource(source) + ".log")

  def append(source: String, level: String, message: String): String = {
    logger.info(message)

    val ts = Instant.now().toString
    val line = s"$ts [$level] $message"
    Files.createDirectories(Config.logsRoot)
    Files.write(
      fileFor(source),
      (line + "\n").getBytes(StandardCharsets.UTF_8),
      java.nio.file.StandardOpenOption.CREATE,
      java.nio.file.StandardOpenOption.APPEND
    )
    message
  }

  /** Resolve a client-supplied log name to a file strictly inside the logs
    * root, or None. The name must be a single path segment (no "/", "\\" or
    * ".."), and the normalised result must still sit directly under the
    * canonical logs root, so nothing outside it (e.g. the secret) can be read
    * or deleted. (VULN #1 was resolving the raw name with no containment.) */
  def safeLogPath(name: String): Option[Path] = {
    if (name.isEmpty || name.contains("/") || name.contains("\\") || name.contains("..") || name.contains("\u0000"))
      None
    else {
      val root   = Config.logsRoot.normalize()
      val target = root.resolve(name).normalize()
      if (target.getParent == root) Some(target) else None
    }
  }

  def listLogFiles(): List[Path] = {
    if (!Files.isDirectory(Config.logsRoot)) Nil
    else
      Files
        .list(Config.logsRoot)
        .iterator()
        .asScala
        .filter(p => Files.isRegularFile(p) && p.getFileName.toString.endsWith(".log"))
        .toList
        .sortBy(_.getFileName.toString)
  }

  def readLines(p: Path): List[String] =
    if (Files.isRegularFile(p)) Files.readAllLines(p, StandardCharsets.UTF_8).asScala.toList
    else Nil

  private def lineTimestamp(line: String): Long =
    scala.util.Try(Instant.parse(line.takeWhile(_ != ' ')).toEpochMilli).getOrElse(0L)

  def recentLines(n: Int): List[String] = {
    val all = listLogFiles().flatMap(readLines)
    all.sortBy(lineTimestamp).takeRight(n)
  }
}

object Render {
  def dashboard(lines: List[String]): String = {
    val body = lines.map(l => s"""        <div class="line">$l</div>""").mkString("\n")
    s"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>LOG — Flight Recorder</title>
  <style>
    body { font-family: monospace; background:#0b0f14; color:#c9d1d9; margin:0; padding:1rem; }
    h1 { font-size:1.1rem; color:#58a6ff; }
    .line { white-space:pre-wrap; border-bottom:1px solid #21262d; padding:2px 0; }
  </style>
</head>
<body>
  <h1>Flight Recorder — recent log lines (${lines.size})</h1>
  <div id="lines">
$body
  </div>
</body>
</html>
"""
  }
}

object Search {
  def run(q: String, source: Option[String]): (Int, List[String]) = {
    val files = source match {
      case Some(s) => List(Config.logsRoot.resolve(Store.sanitizeSource(s) + ".log"))
      case None    => Store.listLogFiles()
    }
    val re = q.r
    val matches = files.flatMap(Store.readLines).filter(line => re.findFirstIn(line).isDefined)
    (matches.size, matches)
  }
}

object Main extends IOApp {

  private def jsonError(msg: String): Json = Json.obj("error" -> Json.fromString(msg))

  private def parseFields(req: Request[IO]): IO[Map[String, String]] = {
    val isJson = req.contentType.exists(_.mediaType == MediaType.application.json)
    if (isJson)
      req.as[String].map { body =>
        parseJson(body).toOption
          .flatMap(_.asObject)
          .map { obj =>
            obj.toMap.flatMap { case (k, v) =>
              v.asString.orElse(if (v.isNull) None else Some(v.noSpaces)).map(k -> _)
            }
          }
          .getOrElse(Map.empty[String, String])
      }
    else
      req
        .as[UrlForm]
        .map(_.values.map { case (k, vs) => k -> vs.headOption.getOrElse("") }.toMap)
        .handleError(_ => Map.empty[String, String])
  }

  // Reconstruct the requested name from the raw (decoded) path segments after
  // /logs/ . Callers validate it with Store.safeLogPath before touching disk.
  private def nameFromRest(rest: Uri.Path): String =
    rest.segments.map(_.decoded()).mkString("/")

  val routes: HttpRoutes[IO] = HttpRoutes.of[IO] {

    case GET -> Root / "health" =>
      Ok("ok")

    case req @ POST -> Root / "ingest" =>
      parseFields(req).flatMap { fields =>
        fields.get("message").filter(_.nonEmpty) match {
          case None => BadRequest(jsonError("message is required"))
          case Some(message) =>
            val source = Store.sanitizeSource(fields.getOrElse("source", "misc"))
            val level  = fields.getOrElse("level", "INFO")
            IO.blocking(Store.append(source, level, message)).flatMap { stored =>
              Ok(
                Json.obj(
                  "stored"  -> Json.True,
                  "source"  -> Json.fromString(source),
                  "level"   -> Json.fromString(level),
                  "message" -> Json.fromString(stored)
                )
              )
            }
        }
      }

    case GET -> Root / "search" :? QParamQ(q) +& QParamSource(source) =>
      IO.blocking(Search.run(q, source)).flatMap { case (count, matches) =>
        Ok(
          Json.obj(
            "q"       -> Json.fromString(q),
            "source"  -> source.fold(Json.Null)(Json.fromString),
            "count"   -> Json.fromInt(count),
            "matches" -> Json.arr(matches.map(Json.fromString): _*)
          )
        )
      }

    case GET -> Root / "dashboard" =>
      IO.blocking(Store.recentLines(Config.dashboardTail)).flatMap { lines =>
        Ok(Render.dashboard(lines)).map(_.withContentType(`Content-Type`(MediaType.text.html)))
      }

    case GET -> "logs" /: rest =>
      val name = nameFromRest(rest)
      // Only a plain file directly inside the logs root may be downloaded;
      // see Store.safeLogPath.
      val target = Store.safeLogPath(name)
      IO.blocking {
        target.filter(t => Files.isRegularFile(t, java.nio.file.LinkOption.NOFOLLOW_LINKS)).map(t => Files.readAllBytes(t))
      }.flatMap {
        case Some(bytes) =>
          Ok(bytes).map(_.withContentType(`Content-Type`(MediaType.text.plain)))
        case None =>
          NotFound(jsonError(s"no such log: $name"))
      }

    case req @ DELETE -> "logs" /: rest =>
      val name = nameFromRest(rest)
      val _ = req.headers.get(org.typelevel.ci.CIString("X-Operator-Token"))
      val target = Store.safeLogPath(name)
      IO.blocking {
        target.exists(t => Files.deleteIfExists(t))
      }.flatMap { existed =>
        Ok(Json.obj("deleted" -> Json.fromBoolean(existed), "name" -> Json.fromString(name)))
      }

    case GET -> Root / "search" =>
      BadRequest(jsonError("q is required"))

    case _ -> Root / "health" =>
      methodNotAllowed("GET")
    case _ -> Root / "ingest" =>
      methodNotAllowed("POST")
    case _ -> Root / "search" =>
      methodNotAllowed("GET")
    case _ -> Root / "dashboard" =>
      methodNotAllowed("GET")
    case _ -> "logs" /: _ =>
      methodNotAllowed("GET, DELETE")
  }

  private def methodNotAllowed(allowed: String): IO[Response[IO]] =
    IO.pure(Response[IO](Status.MethodNotAllowed).withEntity(jsonError(s"method not allowed; use $allowed")))

  object QParamQ      extends QueryParamDecoderMatcher[String]("q")
  object QParamSource extends OptionalQueryParamDecoderMatcher[String]("source")

  val httpApp: HttpApp[IO] = routes.orNotFound

  def run(args: List[String]): IO[ExitCode] = {
    val startup =
      IO.blocking {
        Files.createDirectories(Config.logsRoot)
        Store.warmup()
      } *> IO.println(
        s"[LOG] flight recorder listening on 0.0.0.0:${Config.port} " +
          s"(logs=${Config.logsRoot}, secret=${Config.secretPath})"
      )

    startup *>
      EmberServerBuilder
        .default[IO]
        .withHost(host"0.0.0.0")
        .withPort(Port.fromInt(Config.port).getOrElse(port"8080"))
        .withHttpApp(httpApp)
        .build
        .use(_ => IO.never)
        .as(ExitCode.Success)
  }
}
