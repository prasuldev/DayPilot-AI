ObjC.import("Foundation");

function run() {
    const appPath = $.NSBundle.mainBundle.bundlePath.js;
    const projectPath = $(appPath).stringByDeletingLastPathComponent.js;
    const task = $.NSTask.alloc.init;
    task.launchPath = $(projectPath + "/productivity-app");
    task.arguments = [];
    task.launch;
}
