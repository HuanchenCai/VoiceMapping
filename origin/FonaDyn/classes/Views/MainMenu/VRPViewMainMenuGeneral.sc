// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

VRPViewMainMenuGeneral {
	var mView;

	// Controls
	var mStaticTextShowAs;
	var mListShowAs;
	var mListShow;

	var mStaticTextOutputDirectory;
	var mButtonBrowseOutputDirectory;
	var mStaticTextOutputDirectoryPath;
	var mViewGuiLoad;
	var mLoads;			// array of the last 24 CPU loads

	var mColorMap; 		// for coloring the load % background
	var mLoadPalette;  // ditto


	// Holders for the non-modal Settings dialog
	var mButtonSettingsDialog;
	var mbSettingsLoaded;
	var <newSettings, <oldSettings, >bSettingsChanged;
	var mButtonHelpOptionsDialog;
	var bResetLayout;

	// Multi-line context-help texts

	var myContextHelp =
"The top row controls general things, like the window layout,
the output directory and Settings.";

	var helpOutDirText =
"This is the path to the current output directory.
You can set it by browsing to it,
or with a statement in the Startup file.
(see the Handbook section 3.5.1)";

	var helpLoadMeter =
"Load meter: this shows the proportion of the CPU time available,
that is used to draw the whole FonaDyn window and its graphs.
The percentages are the average and peak loads for the last second.
(Handbook section 3.1.14)";

	var helpShowList =
"Choose a layout of the whole window here.
Press Enter here to unhide all graphs.";


	///// Methods ///////////////////////////////////

	*new { | view |
		^super.new.init(view);
	}

	init { | view |
		var b = view.bounds;
		var static_font = VRPViewMain.staticFont;
		mView = view;
		mView.setProperty(\contextHelp, myContextHelp);
		bSettingsChanged = false;
		mbSettingsLoaded = false;
		bResetLayout = false;
		oldSettings = ~gVRPMain.mContext.model.settings;

		mColorMap = ColorMap.new();
		mColorMap.load("LoadMeter.csv");
		mLoadPalette = mColorMap.smoothPaletteFunc();
		mLoads = List.newUsing(0.02 ! VRPMain.guiUpdateRate.asInteger); // one second's worth

		this addDependant: ~gVRPMain;
		this addDependant: VRPViewMaps.mAdapterUpdate;




		////////////////////////////////////////////////////////////
		////////////////////////////////////////////////////////////

		mStaticTextShowAs = StaticText(mView, Rect())
		.string_("  Show:")
		.font_(static_font);
		mStaticTextShowAs
		.fixedWidth_(mStaticTextShowAs.sizeHint.width)
		.fixedHeight_(35)
		.stringColor_(Color.white);
		mStaticTextShowAs.setProperty(\contextHelp, "This selects a general layout of the main window.");

		mListShowAs = ListView(mView, Rect())
		.items_([
			"Tiled",
			"Gallery",
			"One graph",
			"All tiled",
			"All gallery"
		]);
		mListShowAs
		.fixedHeight_(mListShowAs.minSizeHint.height/1.2)
		.fixedWidth_(mListShowAs.minSizeHint.width + 12)
		.selectionMode_(\single)
		.value_(0)   			// Start in "Tiled" mode
		.font_(static_font)
		.enterKeyAction_({
			bResetLayout = true;
		});
		mListShowAs.setProperty(\contextHelp, helpShowList);

		mListShow = ListView(mView, Rect())
		.visible_(true)
		.font_(static_font)
		.items_([
			"Voice Field",
			"EGG clusters",
			"Phon clusters",
			"Time Plots",
			"Moving EGG",
			"Signal"
		]);
		mListShow
		.fixedHeight_(mListShow.minSizeHint.height/1.2)
		.fixedWidth_(mListShow.minSizeHint.width*1.5)
		.selectionMode_(\single);
		mListShow.setProperty(\contextHelp, "Choose a solo graph here, even a hidden one.");

		////////////////////////////////////////////////////////////
		////////////////////////////////////////////////////////////

		mStaticTextOutputDirectory = StaticText(mView, Rect(0, 0, 100, 0))
		.string_("Output directory:")
		.font_(static_font);
		mStaticTextOutputDirectory
		.fixedWidth_(mStaticTextOutputDirectory.sizeHint.width)
		.fixedHeight_(35)
		.stringColor_(Color.white);
		mStaticTextOutputDirectory.setProperty(\contextHelp, "The directory to which FonaDyn will save your recordings and Log files.");

		mButtonBrowseOutputDirectory = Button(mView, Rect(0, 0, 100, 0))
		.resize_(4)
		.font_(VRPViewMain.qtFont)
		.states_([["Browse…"]])
		.action_{ |b|
			FileDialog(
				{ | path |
					mStaticTextOutputDirectoryPath.string = path.first;
				},
				nil, 2, 0, // Select a single existing directory
				path: mStaticTextOutputDirectoryPath.string;
			);
		};
		mButtonBrowseOutputDirectory.setProperty(\contextHelp, "Press here to browse for and select an output directory.");

		mStaticTextOutputDirectoryPath = TextField(mView, Rect(0, 0, 100, b.height))
		.font_(static_font)
		.enabled_(false)
		.visible_(true)
		.string_( thisProcess.platform.recordingsDir )
		.background_(Color.white);
		mStaticTextOutputDirectoryPath.setProperty(\contextHelp, helpOutDirText);

		////////////////////////////////////////////////////////////
		////////////////////////////////////////////////////////////

		mViewGuiLoad = UserView(mView, Rect(0, 0, 100, 0))
		.enabled_(false)
		.visible_(true)
		.fixedHeight_(22);
		mViewGuiLoad
		.minWidth_(80)
		.font_(VRPViewMain.qtFont)
		.background_(Color.gray);
		mViewGuiLoad.setProperty(\contextHelp, helpLoadMeter);


		mViewGuiLoad.drawFunc_{ arg uv;
			var str, color;
			var smoothedLoad, maxLoad;
			var rc = uv.bounds.moveTo(0, 0);
			var rcSmall;
			var count = mLoads.size;

			// This plots a scrolling load graph for the most recent second.
			// Most of the calculations are done here,
			// that is, only when the meter is visible
			Pen.use {
				smoothedLoad = mLoads.sum / count;	// compute the average load over one second
				maxLoad = mLoads[mLoads.maxIndex] ? 0.01;	// find the max load in the past second
				rcSmall = Rect(rc.left, rc.top, rc.width * smoothedLoad, rc.height);
				color = mLoadPalette.(maxLoad);
				Pen.smoothing_(false);
				Pen.fillColor = color;
				Pen.strokeColor = color; // Color.white;
				Pen.translate(0, rc.height);
				Pen.scale(rc.width, rc.height.neg / count );
				Pen.width = 1;
				mLoads.do { | v, ix | Pen.moveTo(0@(ix+1)); Pen.lineTo(v@(ix+1)) };
				Pen.stroke;
			};
			str = format
			(
				"%\\% | %\\%",
				(smoothedLoad * 100.0).asInteger.asString.padLeft(3, " "),
				(maxLoad * 100.0).asInteger
			);
			str.drawCenteredIn(rc, uv.font, uv.getProperty(\fontColor));
		};

		////////////////////////////////////////////////////////////
		////////////////////////////////////////////////////////////

		mButtonSettingsDialog = Button(mView, Rect(0, 0, 100, 0))
		.resize_(4)
		.font_(VRPViewMain.qtFont)
		.states_([["Settings…"]])
		.maxWidth_(100)
		.action_({
			newSettings = oldSettings.deepCopy;
			VRPSettingsDialog.new(this)
		});
		mButtonSettingsDialog.setProperty(\contextHelp, "Press here to inspect and modify various settings.");

		////////////////////////////////////////////////////////////
		////////////////////////////////////////////////////////////

		mButtonHelpOptionsDialog = Button(mView, Rect(0, 0, 70, 0))
		.font_(VRPViewMain.qtFont)
		.states_([["Help…"]])
		.maxWidth_(60)
		.action_({
			VRPHelpOptionsDialog.new(this)
		});
		mButtonHelpOptionsDialog.setProperty(\contextHelp, "Yes, there is help.");

		mView.layout = HLayout(
			[mStaticTextShowAs, stretch: 1],
			[mListShowAs, stretch: 1],
			[mListShow, stretch: 1],
			[mStaticTextOutputDirectory, stretch: 1],
			[mButtonBrowseOutputDirectory, stretch: 1],
			[mStaticTextOutputDirectoryPath, stretch: 8],
			[nil, stretch: 1],
			[mViewGuiLoad, stretch: 1],
			[mButtonSettingsDialog, stretch: 1],
			[mButtonHelpOptionsDialog, stretch: 1]
		);
		mView.layout.margins_(5);
	}

	stash { | settings |
		var ios = settings.io;
		mbSettingsLoaded = true;
		mStaticTextOutputDirectoryPath.string_(ios.outDir.tr($\\, $/));
	}

	fetch { | settings |
		var gs = settings.general;

		if (settings.waitingForStash, {
			this.stash(settings);
		});

		oldSettings = settings.deepCopy;

		gs.layout = switch( (mListShowAs.value ? 0),
			0, VRPViewMain.layoutGrid,
			1, VRPViewMain.layoutGallery,
			2, VRPViewMain.layoutStack,
			3, VRPViewMain.layoutGridAll,
			4, VRPViewMain.layoutGalleryAll
		);
		if (bResetLayout, {
			gs.layout = gs.layout.neg;
			bResetLayout = false;
		});

		gs.stackType = switch( mListShow.value,
			0, VRPViewMain.stackTypeVRP,
			1, VRPViewMain.stackTypeClusterEGG,
			2, VRPViewMain.stackTypeClusterPhon,
			3, VRPViewMain.stackTypeSampEn,
			4, VRPViewMain.stackTypeMovingEGG,
			5, VRPViewMain.stackTypeSignal
		);

		settings.io.outDir = mStaticTextOutputDirectoryPath.string;

		if (bSettingsChanged, {
			// Keep data UNLESS .clarityThreshold has changed
// 			bTempKeepData = settings.io.keepData;
// 			settings.io.keepData = true; // (settings.vrp.clarityThreshold == newSettings.vrp.clarityThreshold);

			settings.vrp.clarityThreshold = newSettings.vrp.clarityThreshold;
			settings.vrp.wantsContextSave = newSettings.vrp.wantsContextSave;
			settings.io.enabledEGGlisten = newSettings.io.enabledEGGlisten;
			settings.io.enabledWriteLog = newSettings.io.enabledWriteLog;
			settings.io.writeLogFrameRate = newSettings.io.writeLogFrameRate;
			settings.io.keepInputName = newSettings.io.keepInputName;
			settings.io.enabledWriteGates = newSettings.io.enabledWriteGates;
			settings.cluster.suppressGibbs = newSettings.cluster.suppressGibbs;
			settings.io.arrayRecordInputs = newSettings.io.arrayRecordInputs;
			settings.io.enabledRecordExtraChannels = newSettings.io.enabledRecordExtraChannels;
			settings.io.arrayRecordExtraInputs = newSettings.io.arrayRecordExtraInputs;
			settings.io.rateExtraInputs = newSettings.io.rateExtraInputs;
			settings.general.enabledDiagnostics = newSettings.general.enabledDiagnostics;
			settings.general.colorThemeKey = newSettings.general.colorThemeKey;
			settings.general.saveSettingsOnExit = newSettings.general.saveSettingsOnExit;
			settings.general.clusterSortRequested = newSettings.general.clusterSortRequested;
			// settings.vrp.bSingerMode = newSettings.vrp.bSingerMode;
			// this.changed(this, \splRangeChanged, settings.vrp.bSingerMode);

			settings.general.guiChanged_(true);
			settings.waitingForStash_(true);
			bSettingsChanged = false;
			mbSettingsLoaded = false;
		});
	}

	updateData { | data |
		var dsg = data.settings.general;

		if (bSettingsChanged.not and: (mbSettingsLoaded.not), { oldSettings = data.settings });
		if (data.general.starting, { // Disable when starting
			mButtonSettingsDialog.enabled = false;
		});
		if (data.general.stopping, { // Enable when stopping
			mButtonSettingsDialog.enabled = true;
		});
		this.showDiagnostics(data.settings.general.enabledDiagnostics);

		if (dsg.guiChanged, {
			mView.background_(dsg.getThemeColor(\backPanel));
			[mStaticTextShowAs, mStaticTextOutputDirectory].do ({ arg c;
				c.stringColor_(dsg.getThemeColor(\panelText))}
			);
			mViewGuiLoad.background_(dsg.getThemeColor(\backGraph));
			mViewGuiLoad.setProperty(\fontColor, dsg.getThemeColor(\panelText));
		});
		mListShow.visible_(mListShowAs.value == (VRPViewMain.layoutStack-1));  // only for "one graph"

		if (mViewGuiLoad.visible, {
			// mLoads is a FIFO buffer of one second's duration
			mLoads.addFirst(data.general.frameLoad);
			mLoads.pop;
			mViewGuiLoad.refresh;
		});
	}

	showDiagnostics { | bShow |
		[
			mViewGuiLoad
		] do: { | b, i | b.visible_(bShow) };
	}

	close {
		this.release;
	}
}