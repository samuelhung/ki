val repositoryRoot = rootDir.toPath()

allprojects {
    repositories {
        google()
        mavenCentral()
    }
    if (projectDir.toPath().startsWith(repositoryRoot)) {
        dependencyLocking {
            lockAllConfigurations()
            lockMode.set(org.gradle.api.artifacts.dsl.LockMode.STRICT)
        }
        configurations.configureEach {
            if (name.startsWith("_internal-unified-test-platform")) {
                resolutionStrategy.eachDependency {
                    if (
                        requested.group == "io.netty" &&
                            requested.version in setOf("4.1.93.Final", "4.1.110.Final")
                    ) {
                        useVersion("4.1.135.Final")
                    }
                    if (
                        requested.group == "com.google.protobuf" &&
                            requested.version?.startsWith("3.") == true
                    ) {
                        useVersion("3.25.5")
                    }
                    if (requested.group == "org.bouncycastle" && requested.version == "1.79") {
                        useVersion("1.80.2")
                    }
                }
            }
        }
    }
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}
subprojects {
    project.evaluationDependsOn(":app")
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
