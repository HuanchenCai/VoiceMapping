// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

VRPViewMainMenuInput {
	var mView;

	// States
	var mClipping;
	var mClockUpdate;
	var mClockStep;
	var mClockProgress;

	// Controls
	var mCheckBoxKeepData;
	var mButtonStart;
	var mButtonPause;
	var mSetFocusPause;

	var mStaticTextInput;
	var mListInputType;

	var mButtonCalibrate;

	var mButtonBrowse;
	var mStaticTextFilePath;

	var mButtonBrowse2;
	var mStaticTextScriptPath;

	var mUserViewClipping;
	var mFontClipping;

	var mButtonAddFilePath;
	var mButtonRemoveFilePath;
	var mListBatchedFilePaths;
	var mDialProgress;
	var mStaticTextClock;

	// Scripting mechanism
	var mScriptLines;
	var mScriptLineIndex;
	var mScriptState;
	var mScriptLastPath;
	var mScriptFile;
	var mScriptData; // needed for saving maps and cluster data

	// States
	var mLastPath;
	var mThisIndex; // Index into the batched file paths that is being played
	var mPauseNow;
	var mFileChanged;

	classvar canStart = 0;
	classvar setStart = 1;
	classvar waitingForStart = 2;
	classvar canStop = 3;
	classvar setStop = 4;
	classvar waitingForStop = 5;

	classvar fromRecording = 0;
	classvar fromSingleFile = 1;
	classvar fromMultipleFiles = 2;
	classvar fromScript = 3;
	classvar <initScript;

	classvar iNone = 0;		// Not running from a script
	classvar iLoaded = 1;		// A script is loaded but not read
	classvar iReady = 2;		// Ready to continue in script
	classvar iHeld = 3;		// Waiting for user to press START
	classvar iOKtoRun = 4;		// Waiting for .updateData to press START
	classvar iRunning = 5;		// Waiting for this RUN to complete
	classvar iFileDone = 6;	// This RUN has completed
	classvar iFinished = 7;	// Ran to completion for one whole script
	classvar iAborted = 8;		// An error was detected, script was aborted


	////// Multi-line context-help texts ///////////////////

	var helpSourceType =
"Choose the mode of analysis:
- live signals from mic and EGG
- a recorded file with mic and EGG signals
- several signal files, to be processed in sequence
- as instructed from a text script file";

	var helpSignalInputFile =
"After recording, the name of the new file is shown here.
You cannot edit the filename in this field, only copy it for your records.
To open a signal file with at least two channels for analysis, use the Browse button.
You can also drag a signal file to here, if its name ends in \"_Voice_EGG.wav\".";

	var helpBrowseForScript =
"Lets you select a script file for FonaDyn to execute.
Script files are flat text files in the FonaDyn-script syntax.
A script file can have any name, but the convention is *.txt.";

	var helpLastScript =
"The name of the most recent script file.
To run it again, you must select it again.";

	var helpEGGclipping =
"If you see \"EGG CLIPPING\" here, reduce the output voltage of your EGG device.
Reducing the gain on the EGG input of your audio interface might help, too.
Make sure that the Moving EGG waveform does not look clipped.";

	var helpBatchedFilesList =
"A list of currently queued signal files.
The one you select is the one at which analysis starts.
You can drag-and-drop one or more signal files to here,
if their names end in \"_Voice_EGG.wav\".
To add ANY signal file with at least two channels, use the button Add File/-s.";

	//////////////////////////////////


	*new { | view |
		^super.new.init(view);
	}

	*configureInitScript { arg path;
		if (path.isString and:  { File.exists(path) },
			{ initScript = path;
		});
	}

	init { | view |
		var b = view.bounds;
		var static_font = VRPViewMain.staticFont;
		mView = view;
		mView.setProperty(\contextHelp, "The second row holds the controls for choosing the input, and START/STOP/PAUSE" );
		// mLastPath = thisProcess.platform.recordingsDir;
		// mScriptLastPath = thisProcess.platform.recordingsDir;
		mSetFocusPause = false;
		mFileChanged = false;
		mScriptFile = "";
		mScriptLines = [];
		mScriptLineIndex = 0;
		mClockProgress = 0;
		this addDependant: ~gVRPMain;
		this.scriptState_(iNone);

		view onClose: { this.close } ;

		//////////////////////////////////////////////////////////
		//////////////////////////////////////////////////////////

		mStaticTextInput = StaticText(mView, Rect(0, 0, 100, 0))
		.string_("Source:")
		.font_(static_font);
		mStaticTextInput
		.fixedWidth_(mStaticTextInput.sizeHint.width)
		.fixedHeight_(35)
		.stringColor_(Color.white);
		mStaticTextInput.setProperty(\contextHelp, "Selects what signals FonaDyn will analyze" );

		mListInputType = ListView(mView, Rect(0, 0, 112, 0))
		.items_([
			"Live signals",
			"From file",
			"Batch multiple files",
			"Run script"
		]);
		mListInputType.setProperty(\contextHelp, helpSourceType);

		mListInputType
		.fixedHeight_(mListInputType.minSizeHint.height * 0.65)
		.fixedWidth_(mListInputType.minSizeHint.width * 1.8)
		.selectionMode_(\single)
		.font_(static_font)
		.action_({ | list |
			var is_recording = list.value == fromRecording;
			var is_from_file = list.value == fromSingleFile;
			var is_from_batched_files = list.value == fromMultipleFiles;
			var is_from_script = list.value == fromScript;

			// Make the appropriate controls visible according to the Source mode
			mButtonBrowse.visible_(is_from_file);
			mStaticTextFilePath.visible_(is_from_file);
			mButtonBrowse2.visible_(is_from_script);
			mStaticTextScriptPath.visible_(is_from_script);
			mButtonCalibrate.visible_(is_recording);
			mUserViewClipping.visible_(is_recording);
			mButtonAddFilePath.visible_(is_from_batched_files);
			mButtonRemoveFilePath.visible_(is_from_batched_files);
			mListBatchedFilePaths.visible_(is_from_batched_files);
		});

		//////////////////////////////////////////////////////////

		mButtonCalibrate = Button(mView, Rect(0, 0, 100, b.height))
		.visible_(false)
		.font_(VRPViewMain.qtFont)
		.states_([["Calibrate…"]])
		.action_({ | btn |
			FonaDyn.calibrate();
		});
		mButtonCalibrate.setProperty(\contextHelp, "Runs the sound level calibration wizard." );


		//////////////////////////////////////////////////////////

		mButtonBrowse = Button(mView, Rect(0, 0, 100, b.height))
		.visible_(false)
		.font_(VRPViewMain.qtFont)
		.states_([["Browse…"]])
		.action_({ | btn |
			mFileChanged = false;
			VRPMain.openPanelPauseGUI({ | path |
				mLastPath = PathName.new(path).pathOnly;

				// A file at path was selected
				if (path.toLower.endsWith(".txt") or: { path.toLower.endsWith(".csv") }, {
					format("The file \"%\" is probably not a signal file.", path).error;
				}, {
					mStaticTextFilePath.string_(path);
					mFileChanged = true;
					// Make sure the start button is enabled.
					mButtonStart.enabled_(true);
				});
			}, nil, path: mLastPath);
		})
		.canReceiveDragHandler_({ |v| v.class.prClearCurrentDrag; });
		mButtonBrowse.setProperty(\contextHelp, "Lets you select a signal file for analysis.");

		// Disabled TextField rather than StaticText, to easily present the path.
		mStaticTextFilePath = TextField(mView, Rect(0, 0, 100, b.height))
		.keyDownAction_({ true })  // Don't let the user enter file names manually
		.font_(VRPViewMain.staticFont)
		.visible_(false)
		.background_(Color.white)
		.canReceiveDragHandler_({|v, x, y|
			var str, bOK = false;
			v.enabled_(true);
			str = v.class.currentDrag;
			if (str.class == String, {
				if (str.toLower.endsWith("_voice_egg.wav"), {
					bOK = true;
				} , {
					format("Filename issue: %", PathName(str).fileName).warn;
				})
			} );
			bOK
		})
		.receiveDragHandler_({|v, x, y|
			var str;
			str = v.class.currentDrag;
			mStaticTextFilePath.string_(str);
			mLastPath = PathName.new(str).pathOnly;
			mButtonStart.enabled_(true);
		});
		mStaticTextFilePath.setProperty(\contextHelp, helpSignalInputFile);

		//////////////////////////////////////////////////////////
		//////////////////////////////////////////////////////////

		mButtonBrowse2 = Button(mView, Rect(0, 0, 112, b.height))
		.visible_(false)
		.font_(VRPViewMain.qtFont)
		.states_([["Select script…"]])
		.action_({ | btn |
			VRPMain.openPanelPauseGUI(
				{ | path |
					mScriptLastPath = PathName.new(path).pathOnly;

				// A file at path was selected
				if (path.toLower.endsWith(".wav") or: { path.toLower.endsWith(".csv") }, {
					format("The file \"%\" is probably not a script file.", path).error;
				}, {
					mStaticTextFilePath.string_(path);
					mFileChanged = true;
					// Make sure the start button is enabled.
					mButtonStart.enabled_(true);

					// A file at path was selected
					mStaticTextScriptPath.string_(path);
					this.loadScript(path);

					// Make sure the start button is enabled.
					mButtonStart.enabled_(true);
				});
			}, path: mScriptLastPath);
		});
		mButtonBrowse2.setProperty(\contextHelp, helpBrowseForScript);

		// Enabled TextField to easily present the script path.
		mStaticTextScriptPath = TextField(mView, Rect(0, 0, 100, b.height))
		.enabled_(false)
		.visible_(false)
		.background_(Color.white);
		mStaticTextScriptPath.setProperty(\contextHelp, helpLastScript);


		//////////////////////////////////////////////////////////
		//////////////////////////////////////////////////////////

		mClipping = 0;
		mFontClipping = Font.new(\Arial, 24, true, usePointSize: true);

		mUserViewClipping = StaticText(mView, Rect());    // 0, 0, 100, 30
		mUserViewClipping
		.font_(mFontClipping)
		.stringColor_(Color.red)
		.background_(Color.black)
		.string("EGG CLIPPING");
		mUserViewClipping
		.fixedHeight_(mListInputType.bounds.height)
		.fixedWidth_(mListInputType.bounds.width * 3);
		mUserViewClipping.setProperty(\contextHelp, helpEGGclipping);

		//////////////////////////////////////////////////////////
		//////////////////////////////////////////////////////////

		mButtonAddFilePath = Button(mView, Rect())
		.visible_(false)
		.states_([
			["Add File/-s…"]
		]);
		mButtonAddFilePath
		.fixedSize_(mButtonAddFilePath.sizeHint)
		.font_(VRPViewMain.qtFont)
		.action_( { | btn |
			VRPMain.openPanelPauseGUI(
				{ | paths |
					mListBatchedFilePaths.items_(
						(mListBatchedFilePaths.items ? [])
						++
						paths
					);

					mButtonStart.enabled_(
						(mListBatchedFilePaths.items ? []).isEmpty.not
					);
					mThisIndex = (mListBatchedFilePaths.items ?? []).size;
				},
				multipleSelection: true,
				path: mLastPath;
			);
		});

		mButtonAddFilePath.setProperty(\contextHelp, "Lets you queue one or more signal files for analysis.");


		//////////////////////////////////////////////////////////
		//////////////////////////////////////////////////////////

		mButtonRemoveFilePath = Button(mView, Rect())
		.visible_(false)
		.states_([
			["Remove File/-s…"]
		]);
		mButtonRemoveFilePath
		.font_(VRPViewMain.qtFont)
		.fixedSize_(mButtonRemoveFilePath.sizeHint)
		.action_{ | btn |
			var s = mListBatchedFilePaths.selection;
			var items = mListBatchedFilePaths.items ? [];
			mListBatchedFilePaths
			.selection_([])
			.items_(
				items[ Array.iota(items.size).difference(s) ]
			);

			mButtonStart.enabled_(
				(mListBatchedFilePaths.items ? []).isEmpty.not
			);
		};

		mButtonRemoveFilePath.setProperty(\contextHelp, "Lets you remove one or more files from the analysis queue.");

		//////////////////////////////////////////////////////////
		//////////////////////////////////////////////////////////

		mThisIndex = 0;
		mPauseNow = false;

		mListBatchedFilePaths = ListView(mView, Rect())
		.visible_(false)
		.font_(VRPViewMain.staticFont)
		.maxHeight_(120)
		.selectionMode_(\extended);

		mListBatchedFilePaths
		.canReceiveDragHandler_({|v, x, y|
			var dragged, strs, bOK = true;
			v.enabled_(true);
			dragged = v.class.currentDrag;
			strs = (if (dragged.class == String, { Array.with(dragged) } , { dragged }));
			strs do: { |s, i| if (s.class == String, {
				if (s.toLower.endsWith("_voice_egg.wav").not, {
					format("Invalid signal file name: %", PathName(s).fileName).warn;
					bOK = false;
				})
			} , { bOK = false} ) };
			bOK
		})
		.receiveDragHandler_({|v, x, y|
			var dragged, strs;
			dragged = v.class.currentDrag;
			strs = (if (dragged.class == String, { Array.with(dragged) } , { dragged }));
			mListBatchedFilePaths.items_(
				(mListBatchedFilePaths.items ? []) ++ strs
			);
			mLastPath = PathName.new(strs[0]).pathOnly;
			mButtonStart.enabled_(
				(mListBatchedFilePaths.items ? []).isEmpty.not
			);
			mThisIndex = (mListBatchedFilePaths.items ?? []).size;
		});
		mListBatchedFilePaths.setProperty(\contextHelp, helpBatchedFilesList);

		//////////////////////////////////////////////////////////
		//////////////////////////////////////////////////////////

		mCheckBoxKeepData = CheckBox(mView, Rect(0, 0, 100, b.height), "Keep data")
		.visible_(true)
		.value_(false)
		.font_(static_font);

		mCheckBoxKeepData.setProperty(\contextHelp, "Check this box to record more data into the current voice map.");

		//////////////////////////////////////////////////////////
		//////////////////////////////////////////////////////////

		mButtonStart = Button(mView, Rect(0, 0, 100, b.height))
		.font_(VRPViewMain.qtFont)
		.states_([
			["► START"],     // Can start
			["Starting.. "], // Starting..  (not dispatched)
			["Starting..."], // Starting... (dispatched - waiting for completion)
			["■ STOP"],     // Can stop
			["Stopping.. "], // Stopping..  (not dispatched)
			["Stopping..."]  // Stopping... (dispatched - waiting for completion)
		]);
		mButtonStart
		.fixedWidth_(mButtonStart.sizeHint.width)
		.fixedHeight_(mButtonStart.sizeHint.height * 2)
		.action_{ | btn |
			switch (btn.value,
				setStart, {
					mThisIndex = mListBatchedFilePaths.selection.first ? 0;
					mClockUpdate = 0;
					mClockStep = 1;
					mSetFocusPause = true;
					btn.setProperty(\contextHelp, "Stops the recording or analysis.");
				},

				setStop, {
					mThisIndex = (mListBatchedFilePaths.items ?? []).size;
					mClockStep = 0;
					btn.setProperty(\contextHelp, "Starts a recording or an analysis.");
				}
			);

			this.updateMenu();
		};
		mButtonStart.setProperty(\contextHelp, "Starts/stops a recording or an analysis. (F2)");

		//////////////////////////////////////////////////////////
		//////////////////////////////////////////////////////////

		// The Pause button
		mButtonPause = Button(mView, Rect(0, 0, 100, b.height))
		.font_(VRPViewMain.qtFont)
		.states_([
			[ "▐▐  Pause" ],
			[ "► Resume" ]
		]);
		mButtonPause
		.fixedWidth_(mButtonPause.sizeHint.width)
		.fixedHeight_(mButtonStart.sizeHint.height * 2)
		.enabled_(false)
		.action_({ |b|
			mPauseNow = true;
			if (b.value == 1, { mClockStep = 0}, { mClockStep = 1} );
		})
		.visible_(true);
		mButtonPause.setProperty(\contextHelp, "Pauses/resumes a recording or an analysis. (F3)");

		//////////////////////////////////////////////////////////
		////// The progress dial /////////////////////////////////

		mClockProgress = 0;
		mDialProgress = UserView(mView, Rect())
		.visible_(true)
		.drawFunc_( { | uv |
			if (mClockProgress > 0.0, {
				var rc = uv.bounds.moveTo(0, 0);
				Pen.color = Color.gray;
				Pen.addWedge(rc.center, rc.height.half, pi.half.neg, 2pi * mClockProgress);
				Pen.perform(\fill);
				// Pen.stringCenteredIn(
				// 	(mClockProgress * 100).round.asString ++ "%",
				// 	rc,
				// 	static_font,
				// 	mStaticTextInput.stringColor
				// )
			});
		});
		mDialProgress
		.fixedHeight_(mButtonPause.bounds.height - 20)
		.fixedWidth_(mButtonPause.bounds.height - 10);
		mDialProgress.setProperty(\contextHelp, "Shows the progress through the input file.");

		//////////////////////////////////////////////////////////
		/////// The wall clock ///////////////////////////////////

		mClockUpdate = 0;
		mStaticTextClock = StaticText(mView, Rect())
		.visible_(true)
		.font_(Font(\Arial, 32, true, false, true))
		.stringColor_(Color.gray)
		.align_(\right);
		mStaticTextClock
		.fixedWidth_(mStaticTextClock.sizeHint.width*5);
		mStaticTextClock.setProperty(\contextHelp, "Shows the elapsed running time since START.");


		//////////////////////////////////////////////////////////
		//////////////////////////////////////////////////////////

		mView.layout = HLayout(
			[mStaticTextInput, stretch: 1],
			[mListInputType, stretch: 1],
			[mButtonCalibrate, stretch: 1],
			[mButtonBrowse, stretch: 1],
			[mStaticTextFilePath, stretch: 20],
			[mButtonBrowse2, stretch: 1],
			[mStaticTextScriptPath, stretch: 20],
			[mUserViewClipping, stretch: 1],
			[mButtonAddFilePath, stretch: 1],
			[mButtonRemoveFilePath, stretch: 1],
			[mListBatchedFilePaths, stretch: 20],
			[nil, stretch: 3],
			[mCheckBoxKeepData, stretch: 0, align:\right],
			[mButtonStart, stretch: 0, align:\right],
			[mButtonPause, stretch: 0, align:\right],
			10,
			[mStaticTextClock, stretch: 1, align:\right],
			[mDialProgress, stretch: 1, align:\right]
		);
		mView.layout.margins_(5);

		mListInputType.valueAction_(fromSingleFile);   // default mode
		this addDependant: VRPViewMaps.mAdapterUpdate;  // class VRPViewMaps is not init'ed yet...
		this addDependant: ~gVRPMain;

	} /* init */

	start {
		if (mButtonStart.enabled.not, { ^nil });
		switch (mButtonStart.value,
			canStart, { mButtonStart.valueAction = setStart },
			canStop,  { mButtonStart.valueAction = setStop  }
		);
	}

	pause {
		if (mButtonStart.value == canStop, {
			switch (mButtonPause.value,
				0, { mButtonPause.valueAction = 1 },
				1, { mButtonPause.valueAction = 0 }
			);
		})
	}

	updateMenu {
		var not_started = mButtonStart.value == canStart;
		mListInputType.enabled_(not_started);
		mButtonAddFilePath.enabled_(not_started);
		mButtonRemoveFilePath.enabled_(not_started);
		// mListBatchedFilePaths.enabled_(not_started);

		mButtonStart.enabled_(
			(mButtonStart.value == canStart)
			or:
			(mButtonStart.value == canStop);
		);

		if ( mButtonStart.value == canStart, {
			// Enable/Disable the start button if we have/haven't chosen an input file!
			switch (mListInputType.value,
				fromSingleFile, { // From single file
					mButtonStart.enabled_(
						mStaticTextFilePath.string.isEmpty.not
					);
				},

				fromMultipleFiles, { // From multiple batched files
					mButtonStart.enabled_(
						(mListBatchedFilePaths.items ? []).isEmpty.not
					);
				}
			);
		});

		mButtonPause.enabled_(mButtonStart.value == canStop);
		if (mButtonPause.enabled and: mSetFocusPause,
			{ mButtonPause.focus(true); mSetFocusPause = false } );

		if (mClipping > 0, {
			mUserViewClipping.string_("EGG CLIPPING");
			mClipping = mClipping - 1;
		},{
			mUserViewClipping.string_("");
		});

		mDialProgress.refresh;

	} /* updateMenu */

	stash { | settings |
		var str = settings.io.filePathInput ? "";
		if (str.notEmpty, {
			if (this.scriptState > iNone,
				{
					if (settings.io.sanityCheck(settings).not, {
						this.scriptState_(iAborted);
						str = "";
					});
				}
			);
			mStaticTextFilePath.string_(str.tr($\\, $/));
		});
		mLastPath = settings.io.outDir;
		mCheckBoxKeepData.value_(settings.io.keepData);
	}

	fetch { | settings |
		var ios, gs, cs, ds;

		ios = settings.io;
		gs = settings.general;
		cs = settings.cluster;
		ds = settings.csdft;

		if (mLastPath.isNil, { mLastPath = ios.outDir } );

		if ((this.scriptState > iNone)				// A script is in progress
			and: { VRPData.breatheCycles() == 0 } 	// No other outstanding requests
			and: { mButtonStart.value == canStart },
			{
				this.advanceScript(settings);
			}
		);

		if (gs.queueInitScript, {
			this.loadScript(initScript);
			gs.queueInitScript = false;
		});

		if (settings.waitingForStash, {
			this.stash(settings);
		});

		if ( mButtonStart.value == setStart, {
			gs.start = true;
			mButtonStart.value_( waitingForStart );
		});

		if ( mButtonStart.value == setStop, {
			gs.stop = true;
			mButtonStart.value_( waitingForStop );
		});

		if (mListInputType.value.notNil, {
			ios.inputType = switch ( mListInputType.value,
				fromRecording, VRPSettingsIO.inputTypeRecord,
				fromSingleFile, VRPSettingsIO.inputTypeFile,
				fromMultipleFiles, VRPSettingsIO.inputTypeFile,
				fromScript, VRPSettingsIO.inputTypeScript
			);

			ios.filePathInput = switch ( mListInputType.value,
				fromSingleFile, {
					mStaticTextFilePath.string
				},

				fromMultipleFiles, {
					(mListBatchedFilePaths.items ?? [])[mThisIndex]
				},

				fromScript, { "" }  // don't try to open the script text as a signal
			);
		});
		ios.keepData = mCheckBoxKeepData.value;
	} /* fetch */

	updateData { | data |
		var iod = data.io;
		var ios = data.settings.io;
		var gd = data.general;
		var gs = data.settings.general;


		if (gd.aborted, {								// A sanity check failed in VRPMain
			mButtonStart.value_( waitingForStop );
			gd.aborted = false;
		});

		// Did we previously attempt to start the server?
		if ( (mButtonStart.value == waitingForStart) and: gd.starting.not, {
			if (this.scriptState == iHeld, {
				this.scriptState_(iRunning);
			});
			mClockUpdate = 0;
			mClockStep = 1;
			if (gd.started, {
				mButtonStart.value_( canStop );
				if ((mListInputType.value > fromRecording), {
					var s = PathName(ios.filePathInput);
					if (s.asString.notEmpty, {
						format("Analyzing %, in %", s.fileName, s.pathOnly).postln;
					});
				});
			});
		});

		// Did we previously attempt to stop the server?
		if ( (mButtonStart.value == waitingForStop) and: gd.stopping.not, {
			case
			{ this.scriptState == iFileDone } { this.scriptState_(iReady) }
			{ this.scriptState == iRunning } { this.scriptState_(iAborted) }
			; /* end case */
			mClockProgress = 0;
			if (gd.started.not and: { VRPData.breatheCycles == 0 }, { mButtonStart.value_( canStart ) } );
		});

		mScriptData = data;
		// Have we reached eof?
		if ( iod.eof, {
			if (this.scriptState == iRunning, {
				this.scriptState_(iFileDone);
				// mScriptData = data;
			});
			if (mButtonStart.value == canStop, {
				mButtonStart.value_( setStop );
				mThisIndex = mThisIndex + 1;
			});
		});

		// If we can start another one...
		if ( mButtonStart.value == canStart, {
			// ...and we're using batching, and still have items left
			// Then immediately start the next file
			if ( (mListInputType.value == fromMultipleFiles)
				and: (mThisIndex < (mListBatchedFilePaths.items ?? []).size), {
				mButtonStart.value_( setStart );
				mListBatchedFilePaths.selection = mThisIndex.asArray;
			});

			// ...and we're running a script,
			// and are ready to process the next file
			// then continue when server has started again
			if (this.scriptState == iOKtoRun, {
				this.scriptState_(iHeld);
				mButtonStart.valueAction_( setStart );
			});
		});

		if ( iod.clip, {
			mClipping = VRPMain.guiUpdateRate;  	// Flash CLIPPING! for one second
			iod.clip = false;
		});

		if (mButtonStart.value == canStart,
			{
				mButtonPause.value = 0;
				mClockStep = 0;
			}
		);

		if ( mPauseNow,  {
			gd.pause = gd.pause + 1;  // advance the pause state
		});
		mPauseNow = false;

		// Update the wall clock and progress dial
		if ((gd.started and: gd.stopping.not), {
			var d, str, color, load, progress;
			d = mClockUpdate.asFloat / VRPMain.guiUpdateRate;
			if (mClockUpdate.mod(VRPMain.guiUpdateRate) == 0, {
				str = format("%:%",
					(d/60).floor.asInteger.asString,
					d.mod(60).floor.asInteger.asString.padLeft(2, "0")
				);
				mStaticTextClock.string_(str);
			});
			if ((mListInputType.value > fromRecording), {
			    mClockProgress = d / ios.fileDuration
			});
		});
		mClockUpdate = mClockUpdate + mClockStep;

		// Update the appearances
		if (gs.guiChanged, {
			mView.background_(gs.getThemeColor(\backPanel));
			mUserViewClipping.background_(gs.getThemeColor(\backPanel));
			mDialProgress.background_(gs.getThemeColor(\backPanel));
			mStaticTextInput.stringColor_(gs.getThemeColor(\panelText));
			// class CheckBox does not implement .stringColor (!!)
			mCheckBoxKeepData.palette = mCheckBoxKeepData.palette.windowText_(gs.getThemeColor(\panelText));
			mCheckBoxKeepData.palette = mCheckBoxKeepData.palette.window_(gs.getThemeColor(\backPanel));
		});

		this.updateMenu;
	} /* .updateData */

	//////////////////////////////////////////////////
	///  SCRIPT ENGINE
	//////////////////////////////////////////////////

	loadScript { arg scriptFile;
		// Open the file, and read all lines into an array of strings
		// Lines beginning in lower case are assignments into the .settings object.
		// This is done by interpreting SC code.
		// Specifying § as the column delimiter means that it will interpret almost anything.
		// This is useful, but can be a security problem.
		var tmpArray = FileReader.read(scriptFile, skipEmptyLines: true, delimiter: $§);
		// FileReader returns an array of delimited Strings, per line - use only the first one
		mScriptLines = tmpArray.collect({ |v,i| v[0] });
		mScriptLineIndex = 0;
		mScriptData = nil;
		mScriptFile = PathName(scriptFile).fileName;
		this.scriptState_(iReady);
		format("SCRIPT loaded: %", scriptFile).postln;
	}

	scriptState_{ | v |
		switch (v,
			iFinished, { v = iNone; format("SCRIPT completed: %", mScriptFile).postln },
			iAborted,  { v = iNone; format("SCRIPT aborted: %", mScriptFile).postln }
		);
		mScriptState = v;
		// DEBUG ONLY:
		// format("script state: %, start state: %", mScriptState, mButtonStart.value).postln;
	}

	scriptState {
		^mScriptState;
	}

	advanceScript { | settings |
		var str, fName, t, sMod;
		if ( (this.scriptState == iReady)
			 and: ( mScriptLineIndex < mScriptLines.size )
			 and: ( settings.waitingForStash.not ),
			{
				try {
					// get the next loaded line
					str = mScriptLines[mScriptLineIndex].stripWhiteSpace;
					format("%  %", mScriptLineIndex+1, str).postln;	// Echo line to user
					case
						{ str.isEmpty } { /* the line was empty; do nothing */ }
						{ str[0].isLower } {
							settings.edit(str); // Parse the .settings assignment in str
							settings.waitingForStash_(true);
						}

						{ str.beginsWith("HOLD") } {// HOLD
							// Pause parsing
							// Execution begins when user presses START
							// Parsing resumes when the input file has run to completion
							mListInputType.valueAction_(fromSingleFile);
							this.scriptState_(iHeld);
						}

						{ str.beginsWith("RUN")  } {// RUN
							// Pause parsing
							// Execution continues directly with the next input file
							// Parsing resumes when the input file has run to completion
							mListInputType.valueAction_(fromSingleFile);
							this.scriptState_(iOKtoRun);
						}

						{ str.beginsWith("LOAD") } {	// LOAD _cEGG.csv, _cPhon.csv, or _VRP.csv
							fName = interpret(str[5..]).tr($\\, $/);
							case
							{ VRPDataCluster.testSuffix(fName) } {
								var c, h, sc, tmpDC;
								sc = settings.cluster;
								tmpDC = VRPSettingsCluster.new(sc);
								#c, h = tmpDC.loadClusterSettings(fName);
								if (c < 2) {
									"on reading file".error;
									this.scriptState_(iAborted);
								} { sc.pleaseStashThis_(tmpDC) };
							}

							{ VRPDataClusterPhon.testSuffix(fName) } {
								var c, m, sc, tmpSCP;
								sc = settings.clusterPhon;
								tmpSCP = VRPSettingsClusterPhon.new(sc);
								#c, m = tmpSCP.loadClusterPhonSettings(fName);
								if (c < 2) {
									"on reading file".error;
									this.scriptState_(iAborted);
								} { sc.requestStash(tmpSCP) };
							}

							{ VRPDataVRP.testSuffix(fName) } {
								var c, sv, tmpDV;
								sv = settings.vrp;
								tmpDV = VRPDataVRP.new(nil);
								c = tmpDV.loadVRPdata(fName);
								if (c < 2) {
									"on reading file".error;
									this.scriptState_(iAborted);
								} { sv.setLoadedData(tmpDV) };
								settings.waitingForStash_(true);
							}; /* end case */
						}

						{ str.beginsWith("SAVE") } {	// SAVE (here only if EOF was reached)
							fName = interpret(str[5..]);
							if (mScriptData.notNil, {
								// var ds = settings;  // Should be OK provided that a .fetch has happened

								// The end of the filename given for SAVE selects which data to save
								case
								{ VRPDataVRP.testSuffixSmooth(fName) }
								{ // fName ends in _S_VRP.csv, so smooth the map first, and then save it
									var tempVRPdata = VRPDataVRP.new(mScriptData.settings);
									tempVRPdata.interpolateSmooth(mScriptData.vrp);
									tempVRPdata.saveVRPdata(fName);
									if (settings.vrp.wantsContextSave and: { settings.checkMapContext() },
									{
										mScriptData.saveContextScript(PathName(fName));
									});
								}

								{ VRPDataVRP.testSuffix(fName) }
								{	// Save the map as a _VRP.csv
									mScriptData.vrp.saveVRPdata(fName);
									if (settings.vrp.wantsContextSave and: { settings.checkMapContext() },
									{
										mScriptData.saveContextScript();
										settings.vrp.mapSaved = true;
										settings.waitingForStash_(true);
									});
								}

								{ VRPDataCluster.testSuffix(fName) }
								{	// Save the EGG cluster data
									settings.cluster.saveClusterSettings(fName)
								}

								{ VRPDataClusterPhon.testSuffix(fName) }
								{	// Save the phonation cluster data
									settings.clusterPhon.saveClusterPhonSettings(fName)
								}
							}; ); // case; if
						}

						{ str.beginsWith("EVAL") } {	// EVAL
							interpret(str[5..]);
						}
					; // end case
					mScriptLineIndex = mScriptLineIndex + 1;
				} // try
				{  | errType |
					errType.errorString[7..].error;
					this.scriptState_(iAborted);
				} // on error
		}); // if

		if (mScriptLineIndex >= mScriptLines.size, {
			this.scriptState_(iFinished);
			// this.changed(this, \dialogSettings, settings);  // Should not be needed, but...
		});
		^settings
	} /* .advanceScript */

	close {
		this.release;
	}
}

