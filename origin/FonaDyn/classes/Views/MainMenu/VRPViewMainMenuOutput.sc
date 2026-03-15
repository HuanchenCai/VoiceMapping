// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //


VRPViewMainMenuOutput {
	var mView;

	// Controls
	var mButtonPlayback;
	var mButtonLogAnalysis;
	var mStaticTextLogAnalysisPath;
	var mButtonSaveRecording;
	var mButtonSaveRecordingColoring;
	var mStaticTextSaveRecordingPath;
	var mButtonLogCycleDetection;
	var mStaticTextLogCycleDetectionPath;
	var bLogWarningPosted;
	// var mButtonOutputPoints;
	// var mStaticTextOutputPointsPath;
	// var mButtonOutputSampEn;
	// var mStaticTextOutputSampEnPath;
	var mButtonMapPlayStatus;

	// Map listening states
	classvar <iDisabled = 0;
	classvar <iUnavailable = 1;
	classvar <iReadyTrack = 2;
	classvar <iReadyMap = 3;
	classvar <iPlaying = 4;

	// Just edit this array to get custom log file frame rates
	var mListLogFileRatesDict =
		#[	[			-1,		   0, 				 50, 			100, 			300 ],
		["Analysis Log: Off", "Log @ cycles", "Log @ 50 Hz", "Log @ 100 Hz", "Log @ 300 Hz"]];

	//// Multi-line context-help texts //////////////////////////

	var helpPlaybackEcho =
"Sets sound output to Off or Ready.
If you are monitoring through a loudspeaker,
choosing Off can prevent feedback during recording.";

	var helpRecord =
"Sets recording of signals to Off or Ready.
To record the live signals, select Source: Live signals, and choose Ready.
To re-record an existing file, select Source: From file.
(Handbook, section 3.2.)";

	var helpSaveRecordingPath =
"When recording, FonaDyn creates a file name for you - you cannot choose one yourself.
The name is formed from the current date and time when the recording started.
When the recording is done, select the file name here and copy-paste it
into your journal or experimental log, adding your own description.
You can rename signal files, but the filename should end in \"_Voice_EGG.wav\".
(FonaDyn Handbook, section 3.2.)";

	var helpLogAnalysis =
"Turns on the creation of a Log file.
This can be done before analysis or before recording.
\"Log @ cycles\" puts out a new frame of data for every phonated cycle.
Press more times to choose fixed frame rates of 50, 100 or 300 Hz.

The Log file is saved to the Output directory shown in the top row,
which is not necessarily the directory of the current signal file.
Usually you will want first to set the Output directory to be that of the signal file.";

	var helpLogAnalysisPath =
"When making a Log file, FonaDyn names it like the signal file, but ending in \"_Log.aiff\".
To give the Log file a new time-stamped name instead,
go to Settings... and UNcheck the box \"Keep input file name...\".";

	var helpLogCycleDetection =
"Select \"Cycle Log: On\" to create a separate file,
containing the conditioned EGG signal in track 0,
and the EGG cycle markers in track 1.";

	var helpMapPlayStatus =
"Press here to display the current signal file for listening.
If there is a matching Log file in the same directory,
the button shows \"Listen: map\", and you can select segments
for listening by clicking on the voice map.";


	////////////////////////////////////////////////////////////////////

	*new { | view |
		^super.new.init(view);
	}

	init { | view |
		var b = view.bounds;
		var static_font = VRPViewMain.staticFont;
		mView = view;
		mView.setProperty(\contextHelp, "The third row concerns FonaDyn's outputs: sounds and files.");
		bLogWarningPosted = false;

		////////////////////////////////////////////////////////////////////
		////////////////////////////////////////////////////////////////////

		mButtonPlayback = Button(mView, Rect())
		.font_(VRPViewMain.qtFont)
		.states_([
			["Playback/Echo:  Off", Color.black, Color.gray(0.9)],
			["Playback/Echo: Ready", Color.gray(0.7), Color.green(0.3)],
			["Playback/Echo:  On", Color.white, Color.green(0.8)]
		])
		.action_( { |b| if (b.value==2, { b.value = 0 } )});

		mButtonPlayback
		.fixedWidth_(mButtonPlayback.minSizeHint.width * 1.4 )
		.value_(1);
		mButtonPlayback.setProperty(\contextHelp, helpPlaybackEcho);


		////////////////////////////////////////////////////////////////////
		////////////////////////////////////////////////////////////////////

		mButtonSaveRecording = Button(mView, Rect())    // 0, 0, 100, b.height
		.font_(VRPViewMain.qtFont)
		.states_([
			["Record: Off", Color.black, Color.gray(0.9)],			// 0
			["Record: Ready", Color.gray(0.7), Color.red(0.3)],		// 1
			["Recording", Color.white, Color.red(0.8)],				// 2
 			["Re-recording", Color.white, Color.new(1, 0.5, 0)]		// 3 orange
		])
		.action_{ | btn |
			var enabled = btn.value > 0;
			mStaticTextSaveRecordingPath.visible_(enabled);
			if (btn.value > 1, { btn.valueAction = 0 });
		};
		mButtonSaveRecording
		.fixedWidth_(mButtonSaveRecording.sizeHint.width * 1.2);
		mButtonSaveRecording.setProperty(\contextHelp, helpRecord);

		mStaticTextSaveRecordingPath = TextField(mView, Rect(0, 0, 100, b.height))
		.enabled_(true)
		.visible_(false)
		.background_(Color.white);
		mStaticTextSaveRecordingPath.setProperty(\contextHelp, helpSaveRecordingPath);

		////////////////////////////////////////////////////////////////////
		////////////////////////////////////////////////////////////////////

		mStaticTextLogAnalysisPath = TextField(mView, Rect(0, 0, 100, b.height))
		.font_(VRPViewMain.qtFont)
		.enabled_(false)
		.visible_(false)
		.background_(Color.white);

		mButtonLogAnalysis = Button(mView, Rect())		// 0, 0, 100, b.height
		.font_(VRPViewMain.qtFont)
		.states_( mListLogFileRatesDict[1].collect({|str, i| [str]}));
		mButtonLogAnalysis
		.maxWidth_(mButtonLogAnalysis.minSizeHint.width * 1.2)
		.action_{ | btn |
			var enabled = btn.value >= 1;
			mStaticTextLogAnalysisPath.visible_(enabled);
		};
		mButtonLogAnalysis.setProperty(\contextHelp, helpLogAnalysis);
		mStaticTextLogAnalysisPath.setProperty(\contextHelp, helpLogAnalysisPath);

		////////////////////////////////////////////////////////////////////
		////////////////////////////////////////////////////////////////////

		mStaticTextLogCycleDetectionPath = TextField(mView, Rect(0, 0, 100, b.height))
		.enabled_(false)
		.visible_(false)
		.background_(Color.white);

		mButtonLogCycleDetection = Button(mView, Rect(0, 0, 170, b.height));
		mButtonLogCycleDetection.maxWidth_(170)
		.font_(VRPViewMain.qtFont)
		.states_([
			["Cycle Detection Log: Off"],
			["Cycle Log: On"]
		])
		.action_{ | btn |
			var enabled = btn.value == 1;
			mStaticTextLogCycleDetectionPath.visible_(enabled);
		};
		mButtonLogCycleDetection.setProperty(\contextHelp, helpLogCycleDetection);

		////////////////////////////////////////////////////////////////////
		////////////////////////////////////////////////////////////////////

		mButtonMapPlayStatus = Button(mView, Rect());
		mButtonMapPlayStatus
		.font_(VRPViewMain.qtFont)
		.maxWidth_(80)
		.canFocus_(false)     // Don't let the space bar do anything here
		.states_(
		[
			["Listen: off", Color.black, Color.gray], 	// 0 Listening is disabled
			["Listen: no", Color.red(0.8)],     		// 1 enabled but not possible right now
			["Listen: track", Color.yellow, Color.gray],// 2 enabled and possible with track only
			["Listen: map", Color.green(0.8)],   		// 3 enabled and possible with map
			["Playing", Color.white, Color.green(0.8)]	// 4 Listening is in progress
		])
		.action_( { |b|
			VRPDataPlayer.configureMapPlayer(b.value <= iUnavailable);
		})
		.value_(iDisabled);
		mButtonMapPlayStatus.setProperty(\contextHelp, helpMapPlayStatus);

		////////////////////////////////////////////////////////////////////
		////////////////////////////////////////////////////////////////////

		mView.layout = HLayout(
			[mButtonPlayback, stretch: 1],
			[mButtonSaveRecording, stretch: 1],
			[mStaticTextSaveRecordingPath, stretch: 3],
			[mButtonLogAnalysis, stretch: 1],
			[mStaticTextLogAnalysisPath, stretch: 3],
			[mButtonLogCycleDetection, stretch: 1],
			nil,
			[mStaticTextLogCycleDetectionPath, stretch: 3],
			// [mButtonOutputPoints, stretch: 1],
			// [mStaticTextOutputPointsPath, stretch: 3],
			// [mButtonOutputSampEn, stretch: 1],
			// [mStaticTextOutputSampEnPath, stretch: 3],
			[mButtonMapPlayStatus, stretch: 1, align: \right]
		);
		mView.layout.margins_(5);
	} /* init */

	stash { | settings |
		var ios = settings.io;
		var bnState = 0;
		mButtonPlayback.value_(ios.enabledEcho.asInteger);
		if (ios.enabledWriteLog, {
			if (ios.writeLogFrameRate == -1, {
				bnState = 1;
				ios.writeLogFrameRate = 0;
			}, {
				bnState = mListLogFileRatesDict[0].indexOf(ios.writeLogFrameRate)
			});
		});
		if (bnState != mButtonLogAnalysis.value, {
			mButtonLogAnalysis.valueAction_(bnState ? 0);
		});
	}

	fetch { | settings |
		var ios;

		if (settings.waitingForStash, {
			this.stash(settings);
		});

		ios = settings.io;
		ios.enabledEcho = mButtonPlayback.value.odd;
		ios.enabledWriteAudio = (mButtonSaveRecording.value >= 1);
		ios.enabledWriteCycleDetection = mButtonLogCycleDetection.value == 1;
		ios.enabledWriteLog = (mButtonLogAnalysis.value >= 1);
		if (ios.enabledWriteLog, {
			ios.writeLogFrameRate_(mListLogFileRatesDict[0][mButtonLogAnalysis.value])
		});
// ios.enabledWriteOutputPoints = mButtonOutputPoints.value == 1;
// ios.enabledWriteSampEn = mButtonOutputSampEn.value == 1;
		mButtonSaveRecordingColoring = if (ios.inputType == VRPSettingsIO.inputTypeRecord, { 2 }, { 3 });
		mButtonMapPlayStatus.visible_((ios.inputType == VRPSettingsIO.inputTypeFile));
	}

	updateData { | data |
		var nPlaying;
		var iod = data.io;
		var gd = data.general;

		if (mButtonPlayback.value > 0,
			{ if (gd.stopping, { mButtonPlayback.value = 1 },
				{ if (gd.started, { mButtonPlayback.value = 2 })}
			)}
		);
		if (mButtonSaveRecording.value > 0,
			{ if (gd.stopping, { mButtonSaveRecording.value = 1 },
				{ if (gd.started, { mButtonSaveRecording.value = mButtonSaveRecordingColoring })}
			)}
		);

		if (gd.starting, {
//	mStaticTextOutputPointsPath.string = (iod.filePathOutputPoints ?? "").basename;
			mStaticTextLogCycleDetectionPath.string = (iod.filePathCycleDetectionLog ?? "").basename;
			mStaticTextSaveRecordingPath.string = (iod.filePathAudio ?? "").basename;
//	mStaticTextOutputSampEnPath.string = (iod.filePathSampEn ?? "").basename;
			mStaticTextLogAnalysisPath.string = (iod.filePathLog ?? "").basename;
			if ((data.settings.cluster.learn) or: (data.settings.clusterPhon.learn), {
				if ((mButtonLogAnalysis.value >= 1) and: (bLogWarningPosted.not), {
					"Learning is on: cluster numbers in the Log file will be inconsistent.".warn;
					bLogWarningPosted = true; // Avoid repeating the same warning
				})
			});
		});

		if (gd.stopping, {
			bLogWarningPosted = false;
		});

		this.enableInterface(gd.started.not);
		this.showDiagnostics(data.settings.general.enabledDiagnostics);
		mView.background_(data.settings.general.getThemeColor(\backPanel));

		// Show the state of map-listening
		if (data.player.available > 1,
			{ mStaticTextLogAnalysisPath.string = (iod.filePathLog ?? "").basename }
		);
		if (gd.idle,
			{ mStaticTextLogAnalysisPath.visible_(mStaticTextLogAnalysisPath.string.isEmpty.not) },
			{ data.player.setAvailable(0) }
		);

		// If playing, show the segment number
		if ((mButtonMapPlayStatus.value == iPlaying)
			and: { (nPlaying = data.player.getSelectionPlaying) > 0 },
			{ mButtonMapPlayStatus.string = "Playing"+nPlaying.asString }
		);

		// Here the order in which the cases are tested is important
		case
		{ data.player.class.enabled.not }			{ mButtonMapPlayStatus.value_(iDisabled) }
		{ data.player.status
			== VRPDataPlayer.iStatusProcessing } 	{ mButtonMapPlayStatus.value_(iPlaying) }
		{ data.player.status == VRPDataPlayer.iStatusIdle }
			{ case
				{ data.player.available == 1 } 		{ mButtonMapPlayStatus.value_(iReadyTrack) }
				{ data.player.available == 2 } 		{ mButtonMapPlayStatus.value_(iReadyMap) }
			;}
		{ data.player.available == 0 } 				{ mButtonMapPlayStatus.value_(iUnavailable) }
		;
	} /* .updateData */

	enableInterface { | enable |
		[
			mButtonPlayback,
			mButtonSaveRecording,
			mStaticTextSaveRecordingPath,
			mButtonLogAnalysis,
			mButtonLogCycleDetection
			// mButtonOutputPoints,
			// mButtonOutputSampEn
		]
		do: { | ctrl | ctrl.enabled_(enable); };
	}

	showDiagnostics { | bShow |
		[
			mButtonLogCycleDetection,
			// mButtonOutputPoints,
			// mButtonOutputSampEn
		] do: { | b, i | b.visible_(bShow) };
	}

	close {
		nil
	}
}