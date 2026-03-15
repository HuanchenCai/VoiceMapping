// Copyright (C) 2016-2025 by Sten Ternström & Dennis J. Johansson, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

/* This installation utility assumes that files have been unpacked from the ZIP as follows:

	...\Extensions\FonaDyn: including FonaDyn.sc and GridLinesExp.sc.txt
	...\Extensions\FonaDynTools
	...\Extensions\FonaDynTools\win32
	...\Extensions\FonaDynTools\win64
	...\Extensions\FonaDynTools\macos, including a recompiled PitchDetection.scx
	...\Extensions\FonaDynTools\linux

Three of the four subfolders will be deleted during the installation.
*/

FonaDyn {
	classvar fileNameOverrides = "FonaDynOverwrites.sc";
	classvar installPending = "_FonaDynInstallPending.txt";
	classvar <fdExtensions, fdProgram, fdProgramTools, plugsExtensions;
	classvar keyF7, keyF8, charPathDelim;

	*initClass {
		var rr = Routine {
			var instFlag = thisProcess.platform.userAppSupportDir +/+ installPending;

			// If the instFlag file exists, run the install procedure
			// and then delete the file...
			if (File.exists(instFlag), {
				FonaDyn.install(true);
				File.delete(instFlag);
				format("Removed %", instFlag).postln;
			});
		};

		Platform.case (
			\osx, 		{ keyF7 =  98; keyF8 = 100; charPathDelim = $: },	// colon on Mac
			\windows, 	{ keyF7 = 118; keyF8 = 119; charPathDelim = $; },	// semicolon on Windows
			\linux, 	{ keyF7 = 118; keyF8 = 119; charPathDelim = $: }	// not tested on Linux
		);

		// ...but not until the interpreter is ready.
		StartUp.defer (	{
			AppClock.play(rr) ;
			AppClock.sched(2.0, {
				// Install keyboard shortcuts for FonaDyn.run and FonaDyn.rerun
				// These work only when a document has the keyboard focus
				// (I haven't found a good way of setting the focus to a document)
				Document.globalKeyDownAction = Document.globalKeyDownAction.addFunc( { arg doc, char, modifiers, unicode, keyCode ;
					var ret = false;
					if (keyCode == keyF7, { ret = true; "F7: FonaDyn.run".postln;   FonaDyn.run });		// Fn key F7
					if (keyCode == keyF8, { ret = true; "F8: FonaDyn.rerun".postln; FonaDyn.rerun });	// Fn key F8
					ret
				});
			});
		});
	}

	*run { arg bReRun = false;
		var setPathStr;
		var resDir = Platform.resourceDir;
		var currentPath = "PATH".getenv;

		if (currentPath.notNil and: { currentPath.find(resDir, true).isNil }, {
			setPathStr = resDir ++ charPathDelim ++ currentPath;
			"PATH".setenv(setPathStr);
		});

		// Load at least the colors for difference maps
		VRPMetric.configureCVDcolors(colorSetFile: ~colorSetFileName);

		// This can be needed because the user might not
		// be the one who installed FonaDyn for all users
		File.mkdir(thisProcess.platform.userAppSupportDir +/+ "tmp");

		VRPMain.new(bReRun);
	}

	*rerun {
		FonaDyn.run(true);
	}

	*calibrate { arg voiceMicInput, refMicInput;
		FDcal.new(
			voiceMicInput ? VRPControllerIO.audioInputBusIndexVoice,
			  refMicInput ? VRPControllerIO.audioInputBusIndexEGG
		)
	}

	*refreshMfiles { arg whereTo=nil, bEcho=false;
		if (~gVRPMain.notNil, {
			var m = MfSC.new(targetPath: whereTo, echo: bEcho);
			m.updateAllMfiles
		}, {
			"FonaDyn must be running to refresh the m-files".error;
		});
	}

	// Only the (notNil) arguments actually given will be acted upon,
	// so multiple calls to .config can be made in the startup file.
	*config { arg
		inputVoice,
		inputEGG,
		sampleFormat,
		singerMode,
		fixedAspectRatio,
		tileMapsVertically,
		runScript,
		addEGGNotchFilter,
		metricColors, clusterColors,
		colorSet,
		sonicAlerts;

		VRPControllerIO.configureInputs(inputVoice, inputEGG);
		VRPControllerIO.configureSampleFormat(sampleFormat);
		VRPDataVRP.configureSPLrange(singerMode);
		VRPDataVRP.configureAspectRatio(fixedAspectRatio);
		VRPViewMaps.configureTiledMaps(tileMapsVertically);
		VRPViewMainMenuInput.configureInitScript(runScript);

		// If requested, set up a notching pre-filter
		VRPSDIO.configureEGGfilter(addEGGNotchFilter);
		VRPMetric.configureCVDcolors(metricColors, clusterColors, colorSet);
		VRPViewMain.configureSoundAlerts(sonicAlerts);
	}

	*setPaths {
		var fdAllUsers, fdExtPath, plugsAllUsers, plugsPath;

		// Find out if user has copied FonaDyn "per-user", or "system-wide"
		fdExtPath = PathName(VRPMain.class.filenameSymbol.asString.standardizePath).parentPath; // classes
		fdExtPath = PathName(fdExtPath).parentPath; // FonaDyn
		fdExtPath = PathName(fdExtPath).parentPath.asString.withoutTrailingSlash; // Extensions
		fdAllUsers = (fdExtPath == thisProcess.platform.systemExtensionDir);

		if (fdAllUsers,
			{ fdExtensions = thisProcess.platform.systemExtensionDir; },
			{ fdExtensions = thisProcess.platform.userExtensionDir; }
		);

		fdProgram = fdExtensions +/+ "FonaDyn";
		fdProgramTools = fdExtensions +/+ "FonaDynTools";

		// Find out if user has installed SC3Plugins "per-user", or "system-wide"
		plugsPath = PathName(Tartini.class.filenameSymbol.asString.standardizePath).parentPath; // classes
		plugsPath = PathName(plugsPath).parentPath; // PitchDetection
		plugsPath = PathName(plugsPath).parentPath; // SC3plugins
		plugsPath = PathName(plugsPath).parentPath.asString.withoutTrailingSlash; // Extensions
		plugsAllUsers = (plugsPath == thisProcess.platform.systemExtensionDir);

		if (plugsAllUsers,
			{ plugsExtensions = thisProcess.platform.systemExtensionDir; },
			{ plugsExtensions = thisProcess.platform.userExtensionDir; }
		);
	}

	*removeFolder { arg folder;
		File.deleteAll(folder);
	}

	*install { arg bRestartInterpreter=true;
		var success = true;
		var dirName, fName;
		var cmdCompileStr;

		// Check that the SC3 plugins are installed
		// and post instructions if they are not.
		Platform.when(#[\Tartini], {
			FonaDyn.setPaths;
			("Found FonaDyn in" + fdExtensions).postln;
			("Found SC3-plugins in" + plugsExtensions).postln;
			if (Main.versionAtMost(3,13),
				{
					postln ("This SuperCollider is at version" + Main.version + ".");
					postln ("Please update to SuperCollider 3.14.0 or higher before continuing.");
					success = false;
			});

			if (success, {
				File.mkdir(Platform.userAppSupportDir +/+ "tmp");
				success = Platform.case(
					\windows, { cmdCompileStr = "(Ctrl+Shift-L)"; FonaDyn.install_win },
					\osx,     { cmdCompileStr = "(Cmd+Shift-L)";  FonaDyn.install_osx },
					\linux,   { cmdCompileStr = "(Ctrl+Shift-L)"; FonaDyn.install_linux }
				);
			});

			if (success,
				{
					if (bRestartInterpreter, {
						// Move the code for overrides of system methods to the proper location.
						// The .txt file is ignored, and can stay.
						// If invoked from the Install script, this has already been done.
						var fName, dirName = fdExtensions +/+ "SystemOverwrites" ;
						dirName.mkdir;
						fName = dirName +/+ fileNameOverrides;
						if (File.exists(fName),
							{ (fName + "exists - ok,").postln },
							{ File.copy(fdProgram +/+ fileNameOverrides ++ ".txt", fName)}
						);
						thisProcess.recompile;
					} );
					postln ("FonaDyn was installed successfully.");
				},
				{ error ("There was a problem with the installation.") }
			);
		},{
			FonaDyn.promptInstallSC3plugins;
		});
		^success
	} /* .install */

	*install_win {
		var retval = false;

		if (Platform.architecture == 'x86_64', {
			FonaDyn.removeFolder(fdProgramTools +/+ "win32");
			postln ("Installing Win64 plugins");
		}, {
			FonaDyn.removeFolder(fdProgramTools +/+ "win64");
			postln ("Installing Win32 plugins");
		});
		FonaDyn.removeFolder(fdProgramTools +/+ "macos");
		FonaDyn.removeFolder(fdProgramTools +/+ "linux");
		^retval = true
	}

	*install_osx {
		var retval = false;
		// Rename the original PitchDetection.scx so that ours becomes the active one
		// NOTE: in SC3Plugins v3.13.0, the location of PitchDetection.scx
		// is different in the Mac and Windows distrib's (!)
		var scxName = "PitchDetection/PitchDetection.scx";
		var destPath;
		var cmdLine, libDirName;
		var appLibDir = "/Applications/Supercollider.app/Contents/Frameworks";

		destPath = plugsExtensions +/+ "SC3plugins" +/+ scxName;
		if (File.exists(destPath), {
			cmdLine = "mv" + destPath.quote + (destPath ++ ".original").quote;
			cmdLine.postln;
			cmdLine.unixCmd;
			postln (scxName + "overridden.");
		},{
			("Did not find "+ scxName).postln;
		});

		FonaDyn.removeFolder(fdProgramTools +/+ "win32");
		FonaDyn.removeFolder(fdProgramTools +/+ "win64");
		FonaDyn.removeFolder(fdProgramTools +/+ "linux");

		// With SC 3.14.0-1, legacy x64, libsndfile is called as below
		libDirName = appLibDir +/+ "libsndfile.1.0.37.dylib";
		if (File.exists(libDirName), {
			FonaDyn.removeFolder(fdProgramTools +/+ "macos/universal")
		});

		// With SC 3.14.0-1, universal, libsndfile is called as below
		libDirName = appLibDir +/+ "libsndfile.dylib";
		if (File.exists(libDirName), {
			FonaDyn.removeFolder(fdProgramTools +/+ "macos/legacy-x64")
		});

		^true
	}

	*uninstall_osx {
		var retval = false;
		// Restore the name of the original PitchDetection.scx
		var scxName = "PitchDetection/PitchDetection.scx";
		var srcPath, destPath;
		var cmdLine;
		destPath = plugsExtensions +/+ "SC3plugins" +/+ scxName;
		srcPath = destPath ++ ".original";
		if (File.exists(srcPath), {
			cmdLine = "mv" + srcPath.quote + destPath.quote;
			cmdLine.postln;
			cmdLine.unixCmd;
			postln (scxName + "restored.");
		},{
			("Did not find "+ scxName).postln;
		});
		^true
	}

	*install_linux {
		FonaDyn.removeFolder(fdProgramTools +/+ "win32");
		FonaDyn.removeFolder(fdProgramTools +/+ "win64");
		FonaDyn.removeFolder(fdProgramTools +/+ "macos");
		^true
	}

	*uninstall {
		var dirName;
		var fnDoAfterServerQuit, fName, waitRoutine, addFn;

		fnDoAfterServerQuit = {
			FonaDyn.setPaths;
			warn("This removes all FonaDyn code, including any changes you have made.");
			dirName = fdExtensions +/+ "SystemOverwrites" ;
			[fileNameOverrides, "GridLinesExp.sc"] do:
			{ | str |
				fName = dirName +/+ str;
				if (File.exists(fName),	{
					File.delete(fName);
					(fName + "removed.").postln;
				});
			};
			Platform.case(
				\osx,     { FonaDyn.uninstall_osx }
			);

			FonaDyn.removeFolder(fdProgram);
			FonaDyn.removeFolder(fdProgramTools);
			FonaDyn.removeFolder(Platform.userAppSupportDir +/+ "tmp");
 			ServerQuit.remove(addFn, \default);
		};

		waitRoutine = Routine {
			"Stopping all servers...".postln;
			2.wait;
			fnDoAfterServerQuit.();
			thisProcess.recompile;
		};

		if (Server.allRunningServers.isEmpty, {
			fnDoAfterServerQuit.();
			thisProcess.recompile;
		}, {
			addFn = { AppClock.play(waitRoutine) };
			ServerQuit.add( addFn, \default);
			Server.killAll;  // otherwise the plugin binaries won't be deleted
		});
	}

	*promptInstallSC3plugins {
		postln ("The \"SC3 plugins\" are not yet installed.");
		postln ("Download the version for your system,");
		postln ("and follow the instructions in its file README.txt.");
		postln ("Then re-run this installation.");
	}

} /* class FonaDyn */


