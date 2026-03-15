// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

VRPViewPlayer {
	var <signalPathName;
	var <logPathName;
	var mLogDataFrames, mLogDataTracks;
	var mLogFileMetaData;
	var mLogDataNharmonics, mLogDataEggClusters, mLogDataPhonClusters;
	var tmpSignalPathName, preSignalPathName;

	var mSoundFile;
	var mTargetCluster;
	var mTargetClusterType;
	var mSegmentList;
	var mSelectionDSM;

	// Time cursor animation
	var mSampleRate;
	var mAnimateCursorStep;
	var mAnimateCursorPos;

	// Constants
	classvar nameVRPMapPlayer = \sdVRPMapPlayer;
	classvar triggerIDEOS = 119;
	classvar <iSelection = 63;

	// Settings
	var mMinCycles = 1;
	var mToleranceMIDI;
	var mToleranceSPL;
	var mScaleTolerance = 1.0;
	var bToleranceChanged = false;

	// Timing of played segments
	var mMinimumPlayDuration = 0.2; // seconds
	var mFadeDuration; // seconds
	var xFadeDuration; // must be less than mMinimumPlayDuration
	var mRepresentativity = 0.0;  // 0...1

	// Graphics
	var <mView;
	var mUserViewHolder;
	var mSoundFileView;
	var mViewWait;
	var mGridLinesX, mGridView, mDrawGrid;
	var mZoom, mZoomList;
	var mSelectionColor;
	var mPaletteClusters;
	var fnMarkedPalette;
	var mDuration;

	// States
	var <bHiddenByUser;
	var mTargetPoint;
	var mbIdle;
	var mbWarningReported;
	var <mListenEnabled;
	var mListenFileState;
	var mSignalFileHasChanged, mSignalLastChanged;
	var mLogFileNeedsChanging, mLogLastChanged;
	var mConditionPreparing;
	var mnSelections;
	var mnValidCycles;
	var mDisplayCycleTimes;
	var mPlayEGGtoo;
	var mouseButton;
	var mClickedSelection;
	var mEGGframeData, mIxCentroid;


	// Multi-line context-help texts /////////////////////////

	var helpSignal =
"This shows a copy of the signal file, level-normalized.
To listen, make a selection and left-click on it.
The space bar stops the playback.
To (de-)select the whole file, left-double-click.

Pan in time: Right-click and drag horizontally
Zoom in time: Shift-right-click and drag vertically
Zoom to selection: Ctrl-Z
Zoom back: Ctrl-B
Zoom in amplitude: use the mouse wheel

When the Listen button says \"Listen: map\",
- right-clicking a selection marks it with /// in the map
- Ctrl-C displays/hides EGG cycle markers
- F6 plots the metrics chosen in the Plots panel

To see and hear also the EGG signal, push Settings...
and choose \"Play the EGG signal...\".";


	//////////////////////////////////////////////////////////

	// Error messages
	var cautions = #[
		"Any cycles will match",
		"Cell is empty",
		"Cannot listen while analyzing",
		"The signal file is not well specified",
		"The given signal file name does not end in _Voice_EGG.wav",
		"The specified signal file does not exist",
		"A matching Log file does not exist",
		"The signal file was modified more recently than the matching Log file",
		"Cannot listen to multiple files",
		"The given signal file has only one channel"
	];

	////// Class methods /////////////////////////

	*new { | view |
		^super.new.init(view);
	}


	////// Instance methods //////////////////////

	soundFileView {
		^mSoundFileView;
	}

	soundFile {
		^mSoundFile;
	}

	getMyColor { arg cType, cNumber;
		var metric = VRPSettings.metrics[cType];
		var nClusters = mPaletteClusters[cType]; 		// stored by .updateData
		metric.setClusters(0, nClusters);
		^metric.palette.(cNumber);
	}

	// On ctrl-Z, save the current view, and zoom in the indexed selection
	zoomIn { arg sfv, selIndex;
		var firstFrame, frames, tmpFrames;
		var rangeStart, rangeSize;

		firstFrame = (sfv.scrollPos * (sfv.numFrames - sfv.viewFrames)).asInteger;
		frames = [firstFrame, sfv.viewFrames, sfv.yZoom];
		if (frames[1] > 0, {
			mZoomList.add(frames);
			tmpFrames = sfv.selection(selIndex) ++ sfv.yZoom;
			sfv.zoomSelection(selIndex);
			sfv.setSelection(selIndex, [0, 0]);		// Force a redraw of this selection
			sfv.setSelection(selIndex, tmpFrames[0..1]);
			mGridView.refresh;
		});
		// Also update the RangeSlider
		rangeSize = sfv.xZoom / mDuration;
		rangeStart = sfv.scrollPos * (1 - rangeSize);
		mZoom.lo_(rangeStart).range_(rangeSize);
	}

	// On ctrl-B, zoom out to the previous manual selection
	zoomOut { arg sfv, selIndex=63;
		var firstFrame, newFrames, oldFrames;
		if (mZoomList.size > 0, {
			firstFrame = (sfv.scrollPos * (sfv.numFrames - sfv.viewFrames)).asInteger;
			oldFrames = [firstFrame, sfv.viewFrames];
			newFrames = mZoomList.pop;
			sfv.setSelection(selIndex, newFrames[0..1]);
			sfv.zoomSelection(selIndex);
			sfv.setSelection(selIndex, oldFrames);
			sfv.yZoom_(newFrames[2]);
			mGridView.refresh;
		});
		// Also update the RangeSlider
		mZoom.lo_(sfv.scrollPos).range_(sfv.viewFrames.asFloat / sfv.numFrames);
	}

	requestPlot {
		var sendVal, range;
		range = mSoundFileView.selectionSize(63);
		if (range == 0, { sendVal = nil }, { sendVal = this });
		if (mSoundFileView.visible.not, { sendVal = nil });
		this.changed(this, \requestMetricsPlot, sendVal);
	}

	setMapHandler { | vMaps |
		this.addDependant(vMaps);
	}

	init { arg view;
		var range, start;
		mTargetCluster = -2;
		mTargetPoint = 10@10;		// dummy non-nil value
		mDuration = 10.0;			// dummy non-nil value
		mListenEnabled = 0;
		mListenFileState = 0;
		mbWarningReported = false;
		mSignalLastChanged = 0;
		mSignalFileHasChanged = false;
		mLogLastChanged = 0;
		mLogFileNeedsChanging = true;
		mLogFileMetaData = [];

		mbIdle = true;
		signalPathName = "";
		logPathName = "";
		mSoundFile = nil;
		mSelectionDSM = nil;
		mDisplayCycleTimes = false;
		fnMarkedPalette = { | val | Color.black };
		~myVRPViewPlayer = this;
		this.addDependant(VRPViewPlots.mAdapterUpdate);

		mView = view;
		bHiddenByUser = false;
		mUserViewHolder = CompositeView(view, view.bounds);

		// Add a horz grid in seconds
		mGridLinesX = GridLines(ControlSpec(0.0, 1.0, \lin, units: "s"));
		mGridView = UserView.new(mView, Rect());
		mGridView.background_(Color.black);

		mDrawGrid = DrawGrid.new(Rect(), mGridLinesX, nil);
		mDrawGrid
		.gridColors_( [Color.gray(0.3), Color.gray(0.3)] )
		.smoothing_(false)
		.font_(VRPViewMain.gridFont)
		.fontColor_(Color.white);

		if (Main.versionAtLeast(3,13),
			{
				mDrawGrid.tickSpacing_(50,25);
				mDrawGrid.x
				.labelAnchor_(\bottomLeft)
				.labelAlign_(\left)
				.labelOffset_(2@0)
				.drawBoundingRect_(true)
				.labelsShowUnits_(true)
				.labelAppendString_(" s")
				;
			}, {
				mDrawGrid.x.labelOffset.y = mDrawGrid.x.labelOffset.y * VRPMain.screenScale.y * 1.2;
			}
		);

		mZoom = RangeSlider.new(mUserViewHolder, Rect()).orientation_(\horizontal);
		mZoom.lo_(0).range_(1)
		.action_({ |view|
			var divisor, rangeStart;
			rangeStart = view.lo;
			divisor = 1 - view.range;
			if(divisor < 0.0001) {
				rangeStart = 0;
				divisor = 1;
			};
			mSoundFileView.xZoom_(view.range * mDuration)
			.scrollTo(rangeStart / divisor);
			mGridView.refresh;
		});
		mZoom.maxHeight_(25);
		mZoomList = List();

		mSoundFileView = SoundFileView.new(mUserViewHolder, mUserViewHolder.bounds.moveTo(0,0));
		mSoundFileView
		.gridOn_(false)
		.drawsBoundingLines_(false)
		.background_(Color.clear)
		.timeCursorColor_(Color.white)
		.currentSelection_(iSelection);  // for selecting in the signal window
		mSoundFileView.setProperty(\contextHelp, helpSignal);


		mSoundFileView.keyDownAction = { |v, char, mod, unicode, keycode, key|
			var ret_val = nil;
			var setKeys = (49..57);

			// Ignore the keys for playback -- they are handled by VRPViewMain
			case
			{ key == 32 } { ret_val = false }
			{ setKeys.includes(key) } { this.armEggFDs(key-49); ret_val = false }
			{ char.asInteger == 26 } { this.zoomIn(v, 63);  ret_val = false }  	// Ctrl-Z was pressed
			{ char.asInteger ==  2 } { this.zoomOut(v); 	ret_val = false }  	// Ctrl-B was pressed
			{ char.asInteger ==  3 } 											// Ctrl-C was pressed
				{
				mDisplayCycleTimes = mDisplayCycleTimes.not;
				mGridView.refresh;
				}
			{ char.asInteger == 16 } { this.requestPlot; ret_val = false } 		// Ctrl-P was pressed
			{ key == 0x01000000 } { mSoundFileView.setSelectionSize(iSelection, 0) } // ESC to cancel the manual selection
			{ true } { ret_val = v.defaultKeyDownAction(char, mod, unicode, keycode, key)}
			;
			ret_val
		};

		mSoundFileView.mouseDownAction_({ |v, x, y, mod, buttonNumber, clickCount |
			var ret_val = nil, playIx;
			mouseButton = buttonNumber;
			playIx = this.selIndexFromX(v, x);
			if (mouseButton == 0, {
				case
				{ playIx.isNil } { mClickedSelection = -1; mSelectionDSM = nil }
				{ playIx < iSelection  } { mClickedSelection = playIx; ret_val = true }
				{ (playIx == iSelection) and: (mod.isShift.not) }
				{
					mClickedSelection = playIx; ret_val = true;
					// double-click to clear the gray selection
					if (clickCount > 1, {
						v.setSelectionSize(iSelection, 0);
						mClickedSelection = -2;
					});
				};
			});
			if ((mListenEnabled > 1) and: { mouseButton == 1 },
				{
				if ((playIx.notNil) and: { v.selectionSize(playIx) > 0 },
						{   // build a map overlay DSM from selection[playIx]
							mSelectionDSM = this.buildDSM(playIx);
							ret_val = true;
						}, {
							mSelectionDSM = nil;
						}
					);
					// ret_val = true;
			});
			ret_val
		})
		.mouseUpAction_({ |view, x, y, mod|
			mouseButton = nil;
		});

		mSoundFileView.mouseMoveAction_({ |view, x, y, mod|
			var rangeSize, rangeStart;
			if(mouseButton == 1) {
				rangeSize = view.xZoom / mDuration;
				rangeStart = view.scrollPos * (1 - rangeSize);
				mZoom.lo_(rangeStart).range_(rangeSize);
			};
			mGridView.refresh;
		})
		.mouseWheelAction_({|view, x, y, modifiers, xDelta, yDelta |
			view.yZoom = max (1.0, view.yZoom * exp(yDelta/180));
		});

		mGridView.drawFunc_{ | uv |
			var range = mSoundFileView.xZoom;
			var start = mSoundFileView.scrollPos * (mDuration - range);

			// Draw the time axis and grid (in seconds)
			mDrawGrid.x.bounds_(uv.bounds.insetAll(0,0,1,1).moveTo(0, 0));
			mDrawGrid.horzGrid = ControlSpec(start, start+range, \lin, units: "s").grid;
			if (Main.versionAtLeast(3,13), {
				mDrawGrid.x.labelAppendString = " s";
			});
			mDrawGrid.draw;

			// If applicable, draw also the cycle boundaries
			if (mDisplayCycleTimes, {
				// Find all cycle times that are in the displayed range
				var listCycles = this.listDisplayedCycleTimes(start, range);
				var cx, cy, bounds;
				var cColor = Color.new(0.55, 0.0, 0.65);
				bounds = uv.bounds.insetAll(0,0,1,1).moveTo(0, 0);
				Pen.use {
					Pen.strokeColor_(cColor);
					Pen.width_(2.0);
					listCycles.do { | t, ix |
						cx = (t - start).linlin(0, range, 0, bounds.width);
						cy = bounds.height;
						Pen.moveTo(cx@0);
						Pen.lineTo(cx@cy);
					};
					Pen.stroke;
				};
			});


			// If the Signal window is in focus, give mGridView a dark blue border.
			if (mSoundFileView.hasFocus, {
				var bounds = uv.bounds.insetAll(0,0,1,1).moveTo(0, 0);
				var rColor = Color.new(0.1, 0.2, 0.65);
				Pen.use {
					Pen.strokeColor_(rColor);
					Pen.width_(4.0);
					Pen.strokeRect(bounds);
				};
			});
		};

		mSoundFileView.focusGainedAction_({ | v |
			if (mListenFileState < 2, {
				cautions[6].warn;
			});
			mGridView.refresh;
		});


		mSoundFileView.focusLostAction_({ | v |
			mGridView.refresh;
		});

		mView.layout = VLayout(
			mUserViewHolder,
			mZoom
		).margins = [5, 0];

		mUserViewHolder.layout = StackLayout(mSoundFileView.asView, mGridView)
		.mode_(\stackAll)
		.margins_([5, 0])
		.index_(0);

		mSelectionColor = Color.new(1, 1, 0, 0.5);
		mPaletteClusters = Dictionary.newFrom([
			VRPSettings.iClustersEGG,  5,
			VRPSettings.iClustersPhon, 5
		]);

		mSegmentList = List.newClear();
		mLogDataFrames = 0 ! 5;
		mnSelections = 0;
		mIxCentroid = -1;
		mEGGframeData = [];

		// Default settings
		mMinCycles = 1;
		mMinimumPlayDuration = 0.2; // seconds
		mFadeDuration = 0.045; // seconds
		xFadeDuration = 0.045;
		mPlayEGGtoo = false;
		mClickedSelection = -1;
		mToleranceMIDI  = VRPDataPlayer.defaultMidiTol;
		mToleranceSPL   = VRPDataPlayer.defaultLevelTol;
		mSampleRate = Server.default.options.sampleRate ? 44100 ; // in case server has not started yet
		mAnimateCursorPos = 0;
		mAnimateCursorStep = mSampleRate / VRPMain.guiUpdateRate;
		mConditionPreparing = Condition.new(true);
		tmpSignalPathName = thisProcess.platform.userAppSupportDir +/+ "tmp" +/+ "MapListen.wav";
		preSignalPathName = thisProcess.platform.userAppSupportDir +/+ "tmp" +/+ "PreListen.wav";
		mView.onClose_({ | view | this.release; this.close(view) });
	} /* .init */


	// Find out if user has clicked in one of the selections, if any
	selIndexFromX { | sfv, x |
		var clickFrame, viewFirstFrame, viewExtentFrames;
		var ix, matchIx, sf, sels, startTime, totalTime;

		sf = sfv.soundfile.sampleRate;
		sels = sfv.selections;
		totalTime = sfv.soundfile.duration;
		startTime = (totalTime - sfv.xZoom) * sfv.scrollPos;
		viewFirstFrame = startTime * sf;
		viewExtentFrames = sfv.xZoom * sf;

		clickFrame = (x / sfv.asView.bounds.width) * viewExtentFrames + viewFirstFrame;
		ix = 0;
		matchIx = nil;
		while {	matchIx.isNil and: { ix < 64 } }
		{
			if ((sels[ix][0] <= clickFrame) and: { clickFrame <= sels[ix].sum },
				{ matchIx = ix },
				{ ix = ix + 1 }
			)
		};
		^matchIx
	}

	checkMetaData { | settings |
		var s = settings;
		var diffs = [];
		var items = #[
			"Time",
			"Version",
			"Max SPL",
			"Clarity threshold",
			"",
			"",
			"CPP/s",
			"# of EGG clusters",
			"# of PhonType clusters",
			"CSE scaling",
			"Voicing check",
			"Noise threshold",
			"De-noisíng",
			"# of EGG harmonics"
		];
		var localSettings = s.metaData;

		localSettings do: { | item, index |
			var rnd;
			if ((item - mLogFileMetaData[index]).abs > 0.001, {
				diffs = diffs.add (
					rnd = if (items[index][0] == $#, [\asInteger], [\round, 0.01]);
					format("% is % in the Log file but % in the panels.",
						items[index], mLogFileMetaData[index].performMsg(rnd), localSettings[index].performMsg(rnd));
				);
			});
		};
		if (diffs.isEmpty.not, {
			"Differences between the Log file and the current settings:".warn;
			diffs do: { | str | str.postln };
			mLogFileMetaData = [];
		});
	} /* checkMetaData */

	stash { | settings |
		var dummy = 0;
	}

	fetch { | settings |
		var nContext;

		if (Server.default.serverRunning, {
			nContext = this.contextIsValid(settings);
			if (nContext != mListenEnabled, {
				mbWarningReported = false;
				if (nContext > 0, { mListenFileState = nContext } );
			});
			mListenEnabled = nContext;
		});
		mPaletteClusters.add(VRPSettings.iClustersEGG -> settings.cluster.nClusters);
		mPaletteClusters.add(VRPSettings.iClustersPhon -> settings.clusterPhon.nClusters);

		// Show the range slider only in Signal view
		mZoom.visible_( {
			( settings.general.stackType == VRPViewMain.stackTypeSignal ) and:
			( settings.general.layout == VRPViewMain.layoutStack ) }.value
		);

		if (settings.waitingForStash, {
			this.stash(settings);
		});

		// Warn if the Log file does not match the current scenario
		if (mLogFileMetaData.isEmpty.not, {
			this.checkMetaData(settings);
		});
	}

	updateData { | data |
		var scaleChange;
		var dsg = data.settings.general;
		mbIdle = data.general.idle;

		// Set the theme colors
		if (dsg.guiChanged, {
			mView.background_(dsg.getThemeColor(\backGraph));
			mGridView.background_(dsg.getThemeColor(\backGraph));
			mDrawGrid.fontColor_(dsg.getThemeColor(\panelText));
			mGridView.refresh;
			mSoundFileView.background_(Color.clear);
			mZoom.background_(dsg.getThemeColor(\backPanel));
			mZoom.knobColor_(dsg.getThemeColor(\backGraph));
		});

		// If max selections reached, prevent further increase of scaling
		data.player.setMaxReached(mnSelections >= 62);
		data.io.filePathLog = logPathName;

		// Get/Set variables that are used by the VRPViewVRP class
		bToleranceChanged = data.player.scaleTolerance != mScaleTolerance;
		if (bToleranceChanged, {
			// It was changed by VRPViewVRP
			mScaleTolerance = data.player.scaleTolerance;
			mToleranceMIDI  = data.player.midiTolerance();
			mToleranceSPL   = data.player.levelTolerance();
		});
		data.player.representativity = mRepresentativity;
		if (data.player.signalDSM != mSelectionDSM, {
			data.player.signalDSM = mSelectionDSM;
			this.changed(this, \targetOverlay, mSelectionDSM);
		});

		// User has tagged an EGG signal selection
		if (mEGGframeData.notEmpty, {
			data.player.setEggFDs(mIxCentroid, mEGGframeData);
			mEGGframeData = [];
		});

		// Hide the soundfile panel if it is not relevant, or not wanted
		mView.visible =
		(mListenEnabled > -2)
		and: VRPDataPlayer.enabled
		and: bHiddenByUser.not
		and: mbIdle;

		// If all listen-checks are OK
		if (mListenEnabled > 0, {
			if (mListenFileState > 1, { data.io.filePathLog = logPathName } );
			data.player.setAvailable(mListenFileState);
			if (mClickedSelection >= 0, { data.player.markForReplay() });
			this.prepareForListen(mConditionPreparing, data);
		}, {
			if (data.player.playNow.not, { data.player.setAvailable(0) } );
			if (mbWarningReported.not and: (mListenEnabled < -1), {
				format("Can't listen: %", cautions[mListenEnabled.neg]).warn;
				mbWarningReported = true;			// Prevent a cascade of warnings
			})
		});

		// If playback is in progress, animate the cursor too
		if (mConditionPreparing.test.not, {
			mSoundFileView.timeCursorPosition_(mAnimateCursorPos);
			mAnimateCursorPos = mAnimateCursorPos + mAnimateCursorStep;
			// Stop playing if double-clicked
			if (mClickedSelection == -2, {
				data.player.markForStop;
				mClickedSelection = -1;
			});
		});

	} /* .updateData */

	contextIsValid { | settings |
		var strLog, strSig, posSig, mtimeSig, mtimeLog;
		var retVal = mListenFileState;

		// If user has disabled playing then skip
		if (VRPDataPlayer.enabled.not, { ^0 });

		// Must not be running an analysis
		if (mbIdle.not, { ^0 });

		// Skip until any ongoing preparation has finished
		if (mConditionPreparing.test.not, { ^-1 });

		// Must be analyzing a single file(s) - not recording
		if (settings.io.inputType != VRPSettingsIO.inputTypeFile, { ^-2 });

		if (settings.io.filePathInput.class != String, { ^-8 });

		strSig = settings.io.filePathInput.tr($\\, $/) ;

		// A signal file must have been chosen
		if (strSig.isNil or: (strSig.size < 14), { ^-3 });

		// The signal file must have a well-formed name
		posSig = strSig.findBackwards("_Voice_EGG.wav", ignoreCase: true);
		if (posSig.isNil, { ^-4 });

		// Test the following only if a new (or modified) signal file has been specified
		// File.mtime can report +/- 1 second from time to time for the same file (!!??)
		mtimeSig = File.mtime(strSig);
		if (signalPathName != strSig or: { (mtimeSig - mSignalLastChanged).abs > 1 }, {
			retVal = 0;
			mSelectionDSM = nil;

			if (File.exists(strSig).not, { ^-5 });

			// Find out how many channels the input file has
			if (settings.io.inputType == VRPSettingsIO.inputTypeFile(), {
				var nChannels;
				var sf = SoundFile.new;
				sf.openRead(settings.io.filePathInput);
				nChannels = sf.numChannels;
				sf.close;
				if (nChannels < 2, { ^-9 });
			});

			// If we got this far then the signal is OK
			signalPathName = strSig;
			mSignalLastChanged = mtimeSig;
			mSignalFileHasChanged = true;
			retVal = 1;
		});

		// Does a log-file with a matching name also exist?
		strLog = (strSig[0..posSig] ++ "Log.aiff").tr($\\, $/);

		if (File.exists(strLog), {
			// If yes, check also that the signal file hasn't been edited since the Log file was made.
			// The two time stamps could be the same if the signal file was re-recorded with a Log file,
			// or after unzipping the distribution folder; hence the 10-second margin.
			mtimeLog = File.mtime(strLog);
			if (File.mtime(strSig) - 10 > mtimeLog,
				{ ^-7 }
			);
			if (mtimeLog != mLogLastChanged, {
				mLogFileNeedsChanging = true;
				mLogLastChanged = mtimeLog;
			});
			logPathName = strLog;
			retVal = 2;
		}, {
			mLogFileNeedsChanging = false;
			logPathName = "";
			retVal = 1;
		});

		if (mPlayEGGtoo != settings.io.enabledEGGlisten, {
			mSignalFileHasChanged = true
		});
		mPlayEGGtoo = settings.io.enabledEGGlisten;

		// The context is valid
		^retVal;
	} /* .contextIsValid */

	loadSignal { | cond, nChans=1 |
		var buf;
		var c, loadFrame, preSoundFile;

		loadFrame = (0..(nChans-1));	// That is, [0] or [0, 1]

		// This synth plays one segment, and signals "done" a little early,
		// so that the next segment is crossfaded with the current segment.
		// This SynthDef is given here rather than in the SynthDefs folder,
		// because the Player does not use a Controller,
		// and runs only when an analysis does not.
		SynthDef(nameVRPMapPlayer, { arg bufnum=0, frStart=0, dur=0.01, gate=1;
			var sig, env, env2, envelope, xFade, eofSeg;

			env = Env([0,1,1,0], [mFadeDuration, dur, mFadeDuration], [\sine, \lin, \sine]);
			envelope = EnvGen.ar(env, gate, doneAction: 1);
			FreeSelf.kr(Done.kr(envelope));

			env2 = Env([0,1,1,0], [mFadeDuration, dur-(1.5*xFadeDuration), mFadeDuration], \lin);
			xFade = EnvGen.ar(env2, gate);
			eofSeg = Done.kr(xFade);
			SendTrig.kr(eofSeg, triggerIDEOS, -1); // Notify sclang of end-of-segment

			sig = PlayBuf.ar(nChans, bufnum, rate: 1.0, trigger: 1.0, startPos: frStart, loop:  0) * envelope;
			if (nChans == 1, {	Out.ar(0, sig ! 2) }, { Out.ar(0, sig) });
		}).add(\global);

		// Most of these steps are performed by the server,
		// so we have to wait for each one to be completed.
		cond.test = false;
		c = Condition.new(false);

		// Prevent filling of scheduler queue while we are waiting
		~dialogIsOpen = true;

		// Create a temporary file for listening,
		// containing only the first channel (voice),
		// or the two first channels (voice+EGG) if nChans==2
		buf = Buffer.readChannel(Server.default, signalPathName,
			startFrame: 0,
			numFrames: -1,
			channels: loadFrame,
			action: { |b| c.test = true; c.signal }
		);
		this.postWait(format(" Preparing \"%\" for listening", PathName(signalPathName).fileName));
		c.wait;

		// Write always to a 24-bit file
		// so that singerMode is accommodated, if need be.
		c.test = false;
		// buf.write(tmpSignalPathName,
		buf.write(preSignalPathName,
			headerFormat: "wav",
			sampleFormat: "int24",
			numFrames: -1,
			startFrame: 0,
			leaveOpen: false
		);
		buf.server.sync(c);
		buf.close;
		buf.free;

		// Re-load it as a SoundFile
		preSoundFile = SoundFile.new;

		// Normalize it for listening, since the headroom typically is large.
		// If listening also to the EGG,
		// then the normalization is done on both channels separately.
		preSoundFile.openRead(preSignalPathName);

		// "quiet" methods have been added to SoundFile, below
		preSoundFile.quietNormalize(
			outPath: tmpSignalPathName,
			linkChannels: false,
			threaded: true
		);
		if (preSoundFile.isOpen, { preSoundFile.close });
		File.delete(preSignalPathName);

		// Re-load the normalized file as a SoundFile
		if (mSoundFile.notNil, { mSoundFile.close } );
		mSoundFile = SoundFile.new;
		mSoundFile.openRead(tmpSignalPathName);
		mSoundFileView.soundfile = mSoundFile;
		mSoundFileView.waveColors_([Color(0.95, 0.7),  Color(0.55, 0.95)]); // Voice, EGG
		mSoundFileView.selections.do( { |item, index| mSoundFileView.selectNone(index) } );
		mDuration = mSoundFile.numFrames / mSoundFile.sampleRate;
		c.test = false;
		mSoundFileView.read(
			startFrame: 0,
			frames: mSoundFile.numFrames,
			closeFile: true,
			doneAction: { c.test = true; c.signal; }
		);
		c.wait;

		// Signal data are loaded
		mSignalFileHasChanged = false;
		mLogFileNeedsChanging = (mListenEnabled == 2) ;		// we may need to check it again
		cond.test = true;
		cond.signal;
		~dialogIsOpen = false;
	} /* loadSignal */

	loadLogData { | cond |
		var logTracks = #[0, 1, 2, 7, 8];  // time, fo, SPL, cluster#, phoncluster#
		var c, buf, trackData, logFrames;
		var bufMeta, startAt=0;

		// Most of these steps are performed by the server,
		// so we have to wait for each one to be completed.
		c = Condition.new(false);

		// Prevent filling of scheduler queue while we are waiting
		~dialogIsOpen = true;

		// Get the first frame in the matching logFile
		c.test = false;
		bufMeta = Buffer.read(Server.default, logPathName,
			startFrame: 0,
			numFrames: 1,
			action: { |b| /* bufMeta = b; */ c.test = true; c.signal }
		);
		bufMeta.server.sync(c);

		// Test whether that first frame contains metadata;
		// and if so, save it in mLogFileMetaData.
		mLogFileMetaData = [];
		c.test = false;
		bufMeta.getn(0, bufMeta.numChannels, { | a | if (a[0] == -1.0,
			{
				mLogFileMetaData = a;
				startAt = 1;
				c.test = true; c.signal;
			});
		});
		bufMeta.server.sync(c);
		bufMeta.close;
		bufMeta.free;

		// Load the relevant tracks from the matching logFile
		c.test = false;
		buf = Buffer.readChannel(Server.default, logPathName,
			startFrame: startAt,
			numFrames: -1,
			channels: logTracks,
			action: { |b| c.test = true; c.signal }
		);
		buf.server.sync(c);

		// Get the channel data from the server to the client
		c.test = false;
		buf.loadToFloatArray(action: { arg array;
			trackData = array;
			this.postWait(" done.", true);
			c.test = true;
			c.signal;
		});
		buf.server.sync(c);

		// trackData is now a 1-D array, but we want 2D
		logFrames = trackData.reshape((trackData.size/logTracks.size).asInteger, logTracks.size);

		// File data are loaded
		mLogFileNeedsChanging = false;
		buf.close;
		buf.free;
		cond.test = true;
		cond.signal;
		~dialogIsOpen = false;
		^logFrames;
	} /* .loadLogData */

	listDisplayedCycleTimes { arg start, range;
		var jFirst, jLast, tLast;
		var listCycles = List.new(0);
		if (mLogDataTracks.notNil, {
			tLast = start + range;
			jFirst = mLogDataTracks[0].indexOfGreaterThan(start) ? 0;
			jLast = mLogDataTracks[0].indexOfGreaterThan(start + range) ? mLogDataTracks[0].last;
			(jFirst..jLast) do: { | jx |
				listCycles.add (mLogDataTracks[0][jx]);
			}
		});
		^listCycles
	}


	findValidLogFDframe { | time, cond |
		var buf, jFrame, nTracks;
		var frameDuration, fdData = [];

		if (mLogDataTracks.notNil, {		// already loaded
			jFrame  = mLogDataTracks[0].indexOfGreaterThan(time);

			// Skip past the initial metadata frame, if it is present
			if (mLogFileMetaData.isEmpty.not, { jFrame = jFrame + 1 });

			frameDuration = mLogDataTracks[0][jFrame] - mLogDataTracks[0][jFrame-1];
			cond.test = false;
			if ((frameDuration < 50.reciprocal),  {
				var sfTest;
				var c = Condition(false);

				// Find the number of tracks in the logfile (usually 35)
				sfTest = SoundFile.new;
				sfTest.openRead(logPathName);
				nTracks = sfTest.numChannels;
				sfTest.close;

				// Load the relevant frame from the logFile
				buf = Buffer.readChannel(Server.default, logPathName,
					startFrame: jFrame,
					numFrames: 1,
					// the tracks with levels and phases
					channels: ((VRPSDIO.namesArray.size+1)..nTracks-1),
					action: { |b| c.test = true; c.signal }
				);
				buf.server.sync(c);

				// Get the level and phase data from the server to the client
				c.test = false;
				buf.loadToFloatArray(action: { arg array;
					fdData = array;
					c.test = true;
					c.signal;
				});
				buf.server.sync(c);
				buf.close;
				buf.free;

			}, { "Here the clarity and/or the fo is below threshold.".warn });
			cond.test = true;
			cond.signal;
		});
		cond.wait;
		^fdData
	} /* .findValidLogFDframe  */

	armEggFDs { arg ix;
		var time, dur, cond, r;
		dur = mSoundFileView.selectionSize(iSelection) / mSampleRate;
		time = dur + (mSoundFileView.selectionStart(iSelection) / mSampleRate) ;
		cond = Condition.new (false);
		r = Routine {
			mEGGframeData = this.findValidLogFDframe(time, cond);
			mIxCentroid = ix;
		};
		if (dur > 0.0, {
			AppClock.play(r);
		});
	}

	buildSegmentList { arg cond, point, cluster, cType, logData;
		var i, k, cl, clTrack, cycleFirst, segList, bMatch;

		cond.test = false;

		// Find segments of contiguous cycles that meet the search constraints
		// and create a list of such segments
		segList = List.newClear(0);
		i = k = 0;
		clTrack = if (cType == VRPSettings.iClustersPhon, 4, 3);  // select a cluster track

		logData do: { |v, ix| var x, y;
			x  = v[1];  // midi F0
			y  = v[2];	// db SPL
			cl = v[clTrack]; // cluster # v[3]:EGG, v[4]: phontype

			// Are the current cycle data for the requested cell region and cluster?
			bMatch = ((x - point.x).abs <= mToleranceMIDI) and: ((y - point.y).abs <= mToleranceSPL);
			if (bMatch.and(cluster >= 0), {
				bMatch = (cl == cluster);
//	format("cycle: %, cluster: %, found: %, match %", v.round(0.001), cluster, cl, bMatch).postln;
			});
			if (bMatch, {
				// Count consecutive matching cycles
				k = k + 1;
				// Add only the first one to the list
				if (k == 1, {
					cycleFirst = v ++ v[0] ++ k;
				});
				if (k == mMinCycles, {
					segList.add( cycleFirst );
				});
				if (k > mMinCycles, {
					// Still in the same segment: update its endTime and k
					segList.last[5] = v[0];
					segList.last[6] = k;
				})
			}, {
				// Not matching: prepare to start a new segment
				i = i + k;
				k = 0;
			});
		};
		cond.test = true;
		cond.signal;
		^segList;
	} /* .buildSegmentList */

	setSelections { | segList, sfView, minDur = 0.2, color |
		var count = 0;
		var selectionList = List.newClear(mSegmentList.size);
		var selIx = -1;
		var selStart = 0.0, selEnd = 0.0;	// upcoming selection (s)

		segList do: { | v, ix |
			var wStart, wEnd; 		// window (s)
			var selLength;
			var frStart, frLength;  // upcoming selection (frames)
			// SoundFileView supports up to 64 selections;
			// and we reserve index iSelection == 63 for making a manual selection
			if (selIx < (iSelection-1), {
				wStart = max(0.0001, v[0] - mFadeDuration);
				wEnd = v[5] + mFadeDuration;
				if (wStart > selEnd, {
					selIx = selIx + 1;
					selStart = wStart;
				}, {
					selStart = min(selStart, wStart);
				});
				selEnd = max(selEnd, wEnd);
				selLength = selEnd - selStart;
				frStart  = (selStart * mSampleRate).asInteger;
				frLength = (selLength * mSampleRate).asInteger;
				selectionList.put(selIx, [frStart, frLength]);
			});
			count = count + v[6];
		};

		selectionList.do { | frames, ix |
			if (frames.notNil, {
				sfView.setSelection(ix, frames);
				sfView.setSelectionColor(ix, color);
			});
		};
		selIx = selIx + 1;

		if (selIx < iSelection, {
			(selIx..(iSelection-1)) do: { |index| sfView.selectNone(index) };	// Clear the rest
		});

		^[selIx, count]										// Return # of selections and cycles
	} /* .setSelections */

	countSelectedCycles { arg logTranspose, selArray;
		var totalCount = 0;
		var timeTrack = logTranspose[0];
		var tStart = 0.0, tEnd = 0.0;
		var jStart = 0;
		var jEnd = 0;
		var sSize = selArray.size;

		selArray do: { | s, ix |
			tStart = max(0.0, (s[0] - 1) / mSampleRate); // -1 to match .indexOfGreaterThan
			if (tStart < tEnd, {
				// for debug: this should not happen
				format("Selection #% of % overlaps; start: %; end: %", ix, sSize, tStart, tEnd).postln;
			});
			tEnd = (s[0] + s[1] - 1) / mSampleRate;

			// Not very efficient, but seems to be fast enough,
			// this method was benched at 7...20 ms
			jStart = timeTrack.indexOfGreaterThan(tStart);
			jEnd   = timeTrack.indexOfGreaterThan(tEnd) ? timeTrack.size-1 ;
			totalCount = totalCount + (jEnd - jStart);
		};
		^totalCount
	} /* .countSelectedCycles */

	playSelections { arg cond, indeces, player;
		var buf, server, oscFuncEOS;
		var c, r;
		var nSynth, nSelections;
		var arrayFrames = mSoundFileView.selections[indeces];

		server = Server.default;
		c = Condition.new(false);
		mSoundFileView.timeCursorPosition_(0);
		nSelections = arrayFrames.size;

		// Set up an OSCFunc for end-of-selection notification
		// The Condition resides in player so that playback can be interrupted from elsewhere
		oscFuncEOS = OSCFunc({ arg msg, time; player.cond.test = true; player.cond.signal },
			'/tr', server.addr, nil, [nil, triggerIDEOS]
		);

		r = Routine({
			buf = Buffer.read(server, tmpSignalPathName, 0, -1, action: { |b| c.test = true; c.signal });
			c.wait;

			mSoundFileView.timeCursorOn = true;
			block { | stop |
				arrayFrames.do { | sel, ix |
					var startPos, duration;

					player.cond.test = false;
					player.setSelectionPlaying(nSelections-ix);
					startPos = sel[0];
					duration = (sel[1] / mSampleRate) - (2*mFadeDuration);
					nSynth = Synth.new(nameVRPMapPlayer,
						[\bufnum, buf, \frStart, startPos, \dur, duration],
						server,
						\addToHead
					);
					mSoundFileView.timeCursorPosition_(mAnimateCursorPos = startPos);
					player.cond.wait;
					if (player.stopNow(), { nSynth.free; stop.value(ix) });
				};
			};

			// Clean up
			(xFadeDuration * 2).wait; // wait until the last segment has faded out
			player.setSelectionPlaying(0);
			mSoundFileView.timeCursorOn = false;
			buf.close;
			buf.free;
			oscFuncEOS.free;
			cond.test = true;
			cond.signal;
		});

		AppClock.play(r);
	} /* .playSelections */

	// Load the soundfile, and compile the buffers and playlist for listening
	prepareForListen { | cond, data |
		var c, r, selColor, totalCycles;
		var nChans;

		// Important: prevent re-entrancy
		if (cond.test.not, { ^nil });

		c = Condition.new(false);
		r = Routine ({
			if (mSignalFileHasChanged or: mLogFileNeedsChanging, {
				mLogDataFrames = nil;
				mLogDataTracks = nil;
				if (mSignalFileHasChanged, {
					cond.test = false;
					nChans = if (mPlayEGGtoo, 2, 1);
					this.loadSignal(c, nChans);

				});
				if (mLogFileNeedsChanging and: { mListenEnabled > 1 }, {
					c.test = false;
					mLogDataFrames = this.loadLogData(c);
					mLogDataTracks = mLogDataFrames.flop;
					c.wait;
				});
				this.postWait("close");
				mGridView.refresh;
			});
			if (data.player.pending or:	bToleranceChanged, {
				var t = data.player.target();
				var selArray, ixArray;

				cond.test = false;
				c.test = false;
				data.player.markAsBusy();
				mnSelections = 0;
				if (mListenEnabled > 1, {
					mTargetPoint   = t[0];
					mTargetCluster = t[1];
					mTargetClusterType = t[2];
					mSegmentList = this.buildSegmentList(c, mTargetPoint, mTargetCluster, mTargetClusterType, mLogDataFrames);
					c.wait;

					if (mTargetCluster < 0, {
						selColor = mSelectionColor;
					}, {
						selColor = this.getMyColor(mTargetClusterType, mTargetCluster);
					});
					#mnSelections, mnValidCycles = this.setSelections(mSegmentList, mSoundFileView, mMinimumPlayDuration, selColor);
					selArray = mSoundFileView.selections[0..mnSelections-1];
					totalCycles = this.countSelectedCycles(mLogDataTracks, selArray);
					mRepresentativity = mnValidCycles/totalCycles;
					bToleranceChanged = false;

				});

				ixArray = [];
				if (mClickedSelection >= 0,
					{ ixArray = [mClickedSelection] },
					{ if (mnSelections > 0, { ixArray = (0..mnSelections-1) } ) }
				);

				// Queue playbacks, if mouse was shift-clicked (in VRPViewVRP.sc)
				// or the space bar was pressed (in VRPViewMain.sc)
				if (ixArray.isEmpty.not and: { data.player.playNow() }, {
					c.test = false;
					this.playSelections(c, ixArray, data.player );
					c.wait;
				});

				if (mLogDataFrames.notNil and: { mLogDataFrames[0][0] == -1.0 }, {
					// format("Skipping metadata: %", mLogDataFrames.removeAt(0)).postln;
					mLogDataFrames.removeAt(0);
				});

				data.player.markAsHandled();
				mClickedSelection = -1;
			});
			cond.test = true;
			cond.signal;
		});

		AppClock.play(r);

	} /* .prepareForListen */

	// This method scans the selection and builds a DSM
	// for displaying those regions on a map
	buildDSM { arg nSelection;
		var dsm, startTime, endTime, dur;
		var logFirstIndex, logLastIndex;

		dsm = DrawableSparseMatrix.new(VRPDataVRP.vrpHeight+1, VRPDataVRP.vrpWidth+1, fnMarkedPalette);
		startTime = mSoundFileView.selectionStart(nSelection) / mSoundFile.sampleRate;
		dur = mSoundFileView.selectionSize(nSelection) / mSoundFile.sampleRate;
		logFirstIndex = mLogDataTracks[0].indexOfGreaterThan(startTime);
		endTime = min(startTime+dur, mSoundFile.duration);
		logLastIndex = mLogDataTracks[0].indexOfGreaterThan(endTime) ? (mLogDataFrames.size-1);
		mLogDataFrames[logFirstIndex..logLastIndex].do { | frame, ix |
			var idx_midi, idx_spl;
			idx_midi = VRPDataVRP.frequencyToIndex( frame[1] );
			idx_spl = VRPDataVRP.amplitudeToIndex( frame[2] );
			dsm.mark(idx_spl, idx_midi);
		};
		^dsm;
	}

	postWait { arg str, append=false;
		var oldStr = "";
		case
		{ mViewWait.notNil }
		{
			if (str == "close", {
				mViewWait.visible_(false);
				mViewWait.remove;
				mViewWait = nil;
			}, {
				oldStr = mViewWait.string;
				if (append, { mViewWait.string = oldStr ++ str }, { mViewWait.string = str });
				mViewWait.refresh;
			})
		}

		{ str != "close" }
		{
			mViewWait = StaticText.new(mUserViewHolder, Rect(mUserViewHolder).moveTo(0,0));
			mViewWait.font_(Font.new("Arial", 14, true, false));
			mViewWait
			// .string_("Wait - ")
			.background_(Color.blue(0.5, 0.5))
			.stringColor_(Color(0.9, 0.9, 1))
			.string_(str)
			.visible_(true)
			.align_(\topLeft);
			mViewWait.front;
		}
		; /* end of case */
	}

	toggleVisible {
		^bHiddenByUser = bHiddenByUser.not
	}

	close {
		if (mSoundFile.notNil, { mSoundFile.close } );
		File.delete(tmpSignalPathName);
		this.release;
	}

}

	/////////////////////////////////////////////////////////////////
	//////// Here we trim some methods taken from SoundFile,
	//////// to make their posting less verbose (quiet- prefix)
	/////////////////////////////////////////////////////////////////

+ SoundFile {
	quietNormalize { |outPath, newHeaderFormat, newSampleFormat,
		startFrame = 0, numFrames, maxAmp = 1.0, linkChannels = true, chunkSize = 2097152,
		threaded = false|

		var	peak, outFile;

		outFile = this.class.new.headerFormat_(newHeaderFormat ?? { this.headerFormat })
			.sampleFormat_(newSampleFormat ?? { this.sampleFormat })
			.numChannels_(this.numChannels)
			.sampleRate_(this.sampleRate);

			// can we open soundfile for writing?
		outFile.openWrite(outPath.standardizePath).if({
			protect {
				// "Calculating maximum levels...".postln;
				peak = this.quietChannelPeaks(startFrame, numFrames, chunkSize, threaded);
				// Post << "Peak values per channel are: " << peak << "\n";
				peak.includes(0.0).if({
					MethodError("At least one of the soundfile channels is zero. Aborting.",
						this).throw;
				});
					// if all channels should be scaled by the same amount,
					// choose the highest peak among all channels
					// otherwise, retain the array of peaks
				linkChannels.if({ peak = peak.maxItem });
				// "Writing normalized file...".postln;
				this.quietScaleAndWrite(outFile, maxAmp / peak, startFrame, numFrames, chunkSize,
					threaded);
				// "Done.".postln;
			} { outFile.close };
			outFile.close;
			^outFile
		}, {
			MethodError("Unable to write soundfile at: " ++ outPath, this).throw;
		});
	}

	quietChannelPeaks { |startFrame = 0, numFrames, chunkSize = 524288, threaded = false|
		var rawData, peak, numChunks, chunksDone, test;

		peak = 0 ! numChannels;
		numFrames.isNil.if({ numFrames = this.numFrames });
		numFrames = numFrames * numChannels;

			// chunkSize must be a multiple of numChannels
		chunkSize = (chunkSize/numChannels).floor * numChannels;

		if(threaded) {
			numChunks = (numFrames / chunkSize).roundUp(1);
			chunksDone = 0;
		};

		this.seek(startFrame, 0);

		{	(numFrames > 0) and: {
				rawData = FloatArray.newClear(min(numFrames, chunkSize));
				this.readData(rawData);
				rawData.size > 0
			}
		}.while({
			rawData.do({ |samp, i|
				(samp.abs > peak[i % numChannels]).if({
					peak[i % numChannels] = samp.abs
				});
			});
			numFrames = numFrames - chunkSize;
			if(threaded) {
				chunksDone = chunksDone + 1;
				test = chunksDone / numChunks;
				(((chunksDone-1) / numChunks) < test.round(0.02) and: { test >= test.round(0.02) }).if({
					~myVRPViewPlayer.postWait(".", true); //.post;
				});
				0.0001.wait;
			};
		});
		// if(threaded) { $\n.postln };
		^peak
	}

	quietScaleAndWrite { |outFile, scale, startFrame, numFrames, chunkSize, threaded = false|
		var	rawData, numChunks, chunksDone, test;

		numFrames.isNil.if({ numFrames = this.numFrames });
		numFrames = numFrames * numChannels;
		scale = scale.asArray;
//		(scale.size == 0).if({ scale = [scale] });

			// chunkSize must be a multiple of numChannels
		chunkSize = (chunkSize/numChannels).floor * numChannels;

		if(threaded) {
			numChunks = (numFrames / chunkSize).roundUp(1);
			chunksDone = 0;
		};

		this.seek(startFrame, 0);

		{	(numFrames > 0) and: {
				rawData = FloatArray.newClear(min(numFrames, chunkSize));
				this.readData(rawData);
				rawData.size > 0
			}
		}.while({
			rawData.do({ |samp, i|
				rawData[i] = rawData[i] * scale.wrapAt(i)
			});
				// write, and check whether successful
				// throwing the error invokes error handling that closes the files
			(outFile.writeData(rawData) == false).if({
				MethodError("SoundFile writeData failed.", this).throw
			});

			numFrames = numFrames - chunkSize;
			if(threaded) {
				chunksDone = chunksDone + 1;
				test = chunksDone / numChunks;
				(((chunksDone-1) / numChunks) < test.round(0.02) and: { test >= test.round(0.02) }).if({
					~myVRPViewPlayer.postWait(".", true); //.post;
				});
				0.0001.wait;
			};
		});
		// if(threaded) { $\n.postln };
		^outFile
	}

} /* + SoundFile */
