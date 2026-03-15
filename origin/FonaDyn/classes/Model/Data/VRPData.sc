// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
//
// General manager of the data to present in the views.

VRPData {
	var <io;
	var <csdft;
	var <cluster;
	var <clusterPhon;
	var <vrp;
	var <scope;
	var <player;
	var <general;
	var <settings; // A deep copy of the settings made on each start
	var <>trace;
	classvar cyclesToBreathe;

	*new { | s |
		^super.new.init(s);
	}

	*breatheCycles { arg increment=0;
		cyclesToBreathe = max(cyclesToBreathe + increment, 0);
		^cyclesToBreathe
	}

	init { | s |
		settings = s.deepCopy;
		s.class.metrics[VRPSettings.iClarity].minVal = settings.vrp.clarityThreshold;

		io = VRPDataIO(settings);
		csdft = VRPDataCSDFT(settings);
		cluster = VRPDataCluster(settings);
		clusterPhon = VRPDataClusterPhon(settings);
		vrp = VRPDataVRP(settings);
		scope = VRPDataScope(settings);
		// There is no VRPDataPlots
		player = VRPDataPlayer(settings);
		general = VRPDataGeneral(settings);

		cyclesToBreathe = 0;
		trace = \unspecified;
	}

	// This method creates a big multiline string that can be saved as a script.
	// Running that script will restore the context that made the current map.
	mapContextString {  arg mapPathName;
		var lines = List.newClear(0);
		var lineStr, quotedPath, totalStr;

		lineStr = "//// FonaDyn version " ++ VRPMain.mVersion.asString ++ " context script ////";
		lines.add(lineStr);

		lineStr = Date.localtime.format("//// Created %H:%M:%S, %Y-%m-%d");
		lines.add(lineStr);

		lineStr = "io.outDir=" ++ settings.io.outDir.tr($\\, $/).quote;
		lines.add(lineStr);

		lineStr = "io.filePathInput=" ++ settings.io.filePathInput.tr($\\, $/).quote;
		lines.add(lineStr);

		lineStr = "io.enabledWriteLog=" ++ settings.io.enabledWriteLog.asString;
		lines.add(lineStr);

		lineStr = "io.writeLogFrameRate=" ++ settings.io.writeLogFrameRate.asString;
		lines.add(lineStr);

		lineStr = "vrp.clarityThreshold=" ++ settings.vrp.clarityThreshold.asString;
		lines.add(lineStr);

		// Set to false, since we are already running from a context script
		lineStr = "vrp.wantsContextSave=false";
		lines.add(lineStr);

		lineStr = "scope.denoise=" ++ settings.scope.denoise.asString;
		lines.add(lineStr);

		lineStr = "scope.noiseThreshold=" + settings.scope.noiseThreshold.asString;
		// The single "+" above is intentional;
		// it adds a space so that negative numbers will be parsed correctly
		lines.add(lineStr);

		lineStr = "scope.validate=" ++ settings.scope.validate.asString;
		lines.add(lineStr);

		lineStr = "plots.amplitudeWindowSize=" ++ settings.plots.amplitudeWindowSize.asInteger;
		lines.add(lineStr);

		lineStr = "plots.amplitudeHarmonics=" ++ settings.plots.amplitudeHarmonics.asInteger;
		lines.add(lineStr);

		lineStr = "plots.amplitudeSequenceLength=" ++ settings.plots.amplitudeSequenceLength.asInteger;
		lines.add(lineStr);

		lineStr = "plots.amplitudeTolerance=" ++ settings.plots.amplitudeTolerance;
		lines.add(lineStr);

		lineStr = "plots.phaseWindowSize=" ++ settings.plots.phaseWindowSize.asInteger;
		lines.add(lineStr);

		lineStr = "plots.phaseHarmonics=" ++ settings.plots.phaseHarmonics.asInteger;
		lines.add(lineStr);

		lineStr = "plots.phaseSequenceLength=" ++ settings.plots.phaseSequenceLength.asInteger;
		lines.add(lineStr);

		lineStr = "plots.phaseTolerance=" ++ settings.plots.phaseTolerance;
		lines.add(lineStr);

		lineStr = "cluster.initialize=true";
		lines.add(lineStr);

		lineStr = "clusterPhon.initialize=true";
		lines.add(lineStr);

		lineStr = "cluster.learn=false";
		lines.add(lineStr);

		lineStr = "clusterPhon.learn=false";
		lines.add(lineStr);

		lineStr = "LOAD " ++ settings.cluster.filePath.tr($\\, $/).quote;
		lines.add(lineStr);

		lineStr = "LOAD " ++ settings.clusterPhon.filePath.tr($\\, $/).quote;
		lines.add(lineStr);

		quotedPath = mapPathName.fullPath.tr($\\, $/).quote;
		lineStr = "LOAD " ++ quotedPath;
		lines.add(lineStr);

		// Ask VRPSettings to check the file-mod times
		// and alert user if the cluster data has changed.
		lineStr = format("checkClusterFileMods(%)", quotedPath);
		lines.add(lineStr);

		// Context is now complete
		lines.add(format("HOLD // Context restored for %", quotedPath));

		totalStr = "";
		lines.do ( { | str | totalStr = totalStr ++ str ++ "\n" } );
		^totalStr;
	}

	saveContextScript { | pathName=nil |
		var contextStr, pn, n, f, tmp;
		pn = pathName ? vrp.lastPathName;
		if (pn.fullPath.isEmpty, {
			"No map file name has been given, can't save context.".warn;
		}, {
		contextStr = this.mapContextString(pn);
		n = pn.pathOnly +/+ pn.fileName ++ ".Context.txt";
		f = File(n.standardizePath, "w");
		f.write(contextStr);
		f.close;
		("Saved" + n).postln;
		});
	}
}


