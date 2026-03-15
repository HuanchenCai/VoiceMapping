// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

VRPSettingsGeneral {
	// var <output_directory; // Output directory for the session
	var topS;				// Top-level settings
	var <>start; // True if the server should be started
	var <>stop; // True if the server should be stopped
	var <>guiChanged; // True if there are changes pending to the GUI

	var <>layout; // Any of VRPViewMain.layout*
	var <>stackType; // Any of VRPViewMain.stackType*
	var <>enabledDiagnostics;
	var <>saveSettingsOnExit;
	var <>queueInitScript;
	var <>clusterSortRequested;


	var >eval; 	// placeholder variable for evaluating statements in script files - deprecated

	var <colorThemeKey;
	var themes;  // Dictionary of Dictionaries each containing a color theme
	classvar themeColorIndeces = #[\backDrop, \backPanel, \backGraph, \backMap, \backTextField, \panelText, \dullText, \brightText, \curveScope];
	classvar <colorThemeStandard = 0;
	classvar <colorThemeDark = 1;
	classvar <colorThemeStudio = 2;
	classvar <colorThemeMilitary = 3;

	*new { arg topSettings;
		^super.new.init(topSettings);
	}

	init { arg t;
		var theme;
		topS = t;

		topS.io.outDir = thisProcess.platform.recordingsDir;

		start = false;
		stop = false;
		guiChanged = true;
		enabledDiagnostics = false;
		saveSettingsOnExit = false;
		queueInitScript = false;
		clusterSortRequested = true;

		colorThemeKey = VRPSettingsGeneral.colorThemeStandard;
		themes = Dictionary.new;

		// init the csStandard colors ("Grand Piano")
		theme = Dictionary.newFrom( List [
			\backDrop, Color.black,
			\backPanel, Color.gray(0.2),
			\backGraph, Color.black,
			\backMap, Color.white,
			\backTextField, Color.white,
			\panelText, Color.white,
			\dullText, Color.gray(0.5),
			\brightText, Color.white,
			\curveScope, Color.black
		]);
		themes.put(VRPSettingsGeneral.colorThemeStandard, theme);

		// init the csStandard colors ("Night Flight")
		theme = Dictionary.newFrom( List [
			\backDrop, Color.black,
			\backPanel, Color.gray(0.20),
			\backGraph, Color.black,
			\backMap, Color.black,
			\backTextField, Color.white(0.7),
			\panelText, Color.white,
			\dullText, Color.gray(0.4),
			\brightText, Color.white,
			\curveScope, Color.white
		]);
		themes.put(VRPSettingsGeneral.colorThemeDark, theme);

		// init the csStudio colors ("Nordic Deco")
		theme = Dictionary.newFrom( List [
			\backDrop, Color.gray(0.85),
			\backPanel, Color.gray(0.9),
			\backGraph, Color.white,
			\backMap, Color.white,
			\backTextField, Color.white,
			\panelText, Color.gray(0.4),
			\dullText, Color.gray(0.3),
			\brightText, Color.white,
			\curveScope, Color.black
		]);
		themes.put(VRPSettingsGeneral.colorThemeStudio, theme);

		// init the csMilitary colors ("Army Surplus")
		theme = Dictionary.newFrom( List [
			\backDrop, Color.new(0.1, 0.15, 0),
			\backPanel, Color.green(0.18),
			\backGraph, Color.green(0.2),
			\backMap, Color.green(0.2),
			\backTextField, Color.white,
			\panelText, Color.yellow(0.6),
			\dullText, Color.yellow(0.5),
			\brightText, Color.white,
			\curveScope, Color.green
		]);
		themes.put(VRPSettingsGeneral.colorThemeMilitary, theme);
	}

	getThemeColor { arg tColor;
		^themes.at(colorThemeKey).at(tColor);
	}

	colorThemeKey_ { arg themeKey;
		colorThemeKey = themeKey;
		guiChanged = true;
	}

	//// For backward compatibility with v<3.5 //////////
	// Output directory for the session
	output_directory_ { arg dirStr;
		topS.io.outDir = dirStr;
	}

	output_directory {
		^topS.io.outDir;
	}
}
