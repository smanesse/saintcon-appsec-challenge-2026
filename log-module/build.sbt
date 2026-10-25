
ThisBuild / scalaVersion := "2.13.15"
ThisBuild / organization := "com.saintcon"

val http4sVersion = "0.23.30"
val circeVersion  = "0.14.10"

val log4jVersion = "2.14.1"

lazy val root = (project in file("."))
  .settings(
    name := "log-module",
    libraryDependencies ++= Seq(
      "org.http4s"               %% "http4s-ember-server" % http4sVersion,
      "org.http4s"               %% "http4s-dsl"          % http4sVersion,
      "org.http4s"               %% "http4s-circe"        % http4sVersion,
      "io.circe"                 %% "circe-parser"        % circeVersion,
      "org.apache.logging.log4j" %  "log4j-api"           % log4jVersion,
      "org.apache.logging.log4j" %  "log4j-core"          % log4jVersion
    ),
    scalacOptions ++= Seq("-deprecation", "-feature"),

    assembly / mainClass       := Some("com.saintcon.log.Main"),
    assembly / assemblyJarName := "app.jar",
    assembly / assemblyMergeStrategy := {
      case PathList("META-INF", "MANIFEST.MF")        => MergeStrategy.discard
      case PathList("META-INF", "services", _ @ _*)   => MergeStrategy.concat
      case x if x.endsWith(".SF") || x.endsWith(".DSA") || x.endsWith(".RSA") =>
        MergeStrategy.discard
      case x if x.endsWith("module-info.class")       => MergeStrategy.discard
      case _                                          => MergeStrategy.first
    }
  )
