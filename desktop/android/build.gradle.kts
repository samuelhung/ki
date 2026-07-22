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
