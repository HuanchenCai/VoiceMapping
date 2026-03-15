// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

// This class was originally for a dedicated SampEn plotter.
// It has been promoted to a more general plotter.

VRPViewPlots {
	// Views
	var mView;
	var mTableView;
	var mScopeViewer;
	var mViewCSE, mViewCSEwindow;

	///// Old Controls ///////////////////////
	var mStaticTextSampEn;
	var mStaticTextAmplitude;
	var mStaticTextPhase;
	var mStaticTextTolerance;
	var mStaticTextWindowSize;
	var mStaticTextSequenceLength;
	var mStaticTextHarmonics;

	var mNumberBoxToleranceAmplitude;
	var mNumberBoxWindowSizeAmplitude;
	var mNumberBoxSequenceLengthAmplitude;
	var mNumberBoxHarmonicsAmplitude;

	var mNumberBoxTolerancePhase;
	var mNumberBoxWindowSizePhase;
	var mNumberBoxSequenceLengthPhase;
	var mNumberBoxHarmonicsPhase;

	var mCurveColors;
	var mHeadingFont;

	///// New Controls ///////////////////////
	var metricTable;
	var mCPPsymbol;
	var mIdleGraphsRequested;

	// Time-scaling
	var mbMouseDown, mXstart, mXnow, mXscale, mbStretchOK;
	var mTempDuration, mNewDuration;

	// States
	var bSignalPlotPending;
	var signalMetricsData;

	var mContextHelp =
	"This panel optionally graphs up to nine metrics over time.";

	var helpScopeView =
"Plots: Each fleck represents one phonatory cycle,
or one analysis frame (every 23 ms).
The vertical axis 0...1 suits four of the available metrics.
The rest are scaled as shown in the \"Plot Metric\" table.

To change the time scale, do left-click-drag-sideways here.
You need to do this before pressing START.";

	var helpTableView =
"Check a box to select that metric for plotting.
If the signal window is visible, you can select a part of the signal
and then press F6 to have the chosen metrics plotted for that part.

When running, the chosen metrics are plotted over real time.";

	var helpCSEView =
"These numbers control the CSE computation.";


	// Constants
	classvar nMinSampleEntropy = -0.01; // Minimum sample entropy point written
	classvar boxWidth  = 32;
	classvar boxHeight = 22;
	classvar <mAdapterUpdate;

	// Settings

	*initClass {
		mAdapterUpdate = { "initClass Plots".postln }; // Dummy func until instantiated
	}

	*new { | view |
		^super.new.init(view);
	}

	makeMetricTable {
		//// VRPSettings.iLastMetric is the highest index of any non-clustered metric
		var guiMetrics = VRPSettings.metrics[1..VRPSettings.iLastMetric];
		var table = [nil ! 8] dup: guiMetrics.size;

		guiMetrics do: { arg met, i;
			var mx = met.class.symbol;
			var ix = i;
			var msg, newMsg;

			if (ix.notNil, {
				// Get the default values
				table[ix] = [
					met.class.symbol,
					met.plotMin,
					met.plotMax,
					met.unit,
					met.class.busName,
					met.class.busRate,
					met.class.logFileTrack.value,
					if ([\Clarity, \CPP, \CPPs].includes(met.class.symbol), "frame", "cycle")
				];
			});
		};
		^table
	}


	init { | view |
		var gl1, gl2, hl2, vGap;

		mView = view;
		mNewDuration = 2.0;  // default duration of time plots
		mXscale = 1.0;
		bSignalPlotPending = false;
		signalMetricsData = nil;
		mIdleGraphsRequested = [];
		mCPPsymbol = VRPDataVRP.cppStr;
		mHeadingFont = VRPViewMain.staticFont.deepCopy;

		this.initMenu;
		this.initMenuCSE;

		// Create a popup window with the CSE controls

		// Create the scope viewer
		mScopeViewer = ScopeViewer(mView,
			ControlSpec(-1, 0, units: "s"),
			ControlSpec(-0.01, 1.05, units: "")
		);
		mScopeViewer.background_(Color.black);

		mAdapterUpdate = { | menu, who, what, newValue |
			this.update(menu, who, what, newValue);
		};

		///// Implement mouse-drag control of the plot duration  ///////////
		mbMouseDown = false;
		mbStretchOK = true;

		mScopeViewer.viewGrid.mouseDownAction = { arg view, x, y, modifiers, buttonNumber, clickCount;
			if (mbStretchOK, {
				mXstart = view.bounds.width - x;
				mbMouseDown = true;
			});
		};

		mScopeViewer.viewGrid.mouseMoveAction = { arg view, x, y, modifiers;
			if (mbMouseDown, {
				mXnow   = (view.bounds.width - x).clip(0, view.bounds.width);
				mXscale = mXstart.asFloat / mXnow.asFloat;
				this.updateGraphOnly;
			});
		};

		mScopeViewer.viewGrid.mouseUpAction = { arg view, x, y, modifiers, buttonNumber, clickCount;
			if (mbStretchOK, {
				mbMouseDown = false;
				mXscale = 1.0;
				mXstart = mXnow;
				mNewDuration = mTempDuration;
			});
		};

		// Context help for the graph
		mScopeViewer.view.setProperty(\contextHelp, helpScopeView);

		mView.layout_(
			VLayout(
				[ mScopeViewer.view, stretch: 5],
				[ mTableView, stretch: 2 ]
		    )
		);
		mView.layout.spacing_(1);
		mView.layout.margins_(5);
		mView.setProperty(\contextHelp, mContextHelp);
	} /* .init */

	initMenu {
		var static_font = VRPViewMain.staticFont;
		var general_font = mHeadingFont;
		var nColors;

		metricTable = this.makeMetricTable;

		// Create a table with a checkbox for every plottable metric
		mTableView = TreeView.new(mView, Rect(0, 0, mView.bounds.width, 100));
		mTableView.columns =
		["     Plot Metric", "@ 0", "@ 1", "Unit", "Update" /*, "Bus", "Rate" */ ];
		[100, 50, 50, 50, 50 /*, 50, 20 */] do: { | w, ix | mTableView.setColumnWidth(ix, w) };
		metricTable do: { | item, ix |
			var anItem, cellStr, cv;
			mTableView.addItem( item[(0..3)++7].collect { | i | i.asString } );
			anItem = mTableView.itemAt(ix);

			cellStr = anItem.strings[0];
			anItem.setString(0, "");
			cv = CheckBox.new(mTableView);
			cv.string_(cellStr);
			anItem.setView(0, cv);
			if (cellStr == "CSE", {
				cv.action_( { |b| this.sampEnControlsVisible(b.value) } );
			});
		};
		mTableView.maxHeight_(metricTable.size * 25);

		// Fill the check boxes with colours
		nColors = mTableView.numItems;
		mCurveColors = nColors collect: { |v| Color.hsv(v/(nColors+1), 0.7, 0.85) };
		nColors do: { | i |
			var cb;
			cb = mTableView.itemAt(i).view(0);
			cb.palette = cb.palette.base_(mCurveColors[i]);
		};

		mTableView.setProperty(\contextHelp, helpTableView);
	}

	initMenuCSE {
		var static_font = VRPViewMain.staticFont;
		var general_font = Font(\Arial, 9, italic: true, usePointSize: true);
		var vGap, gl2, myBounds;
		myBounds = Rect.new(50, 50, 300, 125);

		mViewCSEwindow = Window.new("CSE settings", myBounds, resizable: false);
		mViewCSEwindow.alwaysOnTop_(true);

		mViewCSE = mViewCSEwindow.asView;
		mViewCSE.deleteOnClose_(false);

		mStaticTextSampEn = StaticText(mViewCSE, Rect())
		.string_("SampEn")
		.font_(general_font);
		mStaticTextSampEn
		.fixedWidth_(mStaticTextSampEn.sizeHint.width)
		.stringColor_(Color.white);

		mStaticTextAmplitude = StaticText(mViewCSE, Rect())
		.string_(" L ")
		.font_(general_font);
		mStaticTextAmplitude
		.fixedWidth_(mStaticTextAmplitude.sizeHint.width)
		.stringColor_(Color.white);

		mStaticTextPhase = StaticText(mViewCSE, Rect())
		.string_(" φ ")
		.font_(general_font);
		mStaticTextPhase
		.fixedWidth_(mStaticTextPhase.sizeHint.width)
		.stringColor_(Color.white);
		boxWidth  = mStaticTextPhase.sizeHint.width*2;
		boxHeight = mStaticTextPhase.sizeHint.height*1.5;

		////////////////////////////////////////////////////////////
		////////////////////////////////////////////////////////////

		mStaticTextTolerance = StaticText(mViewCSE, Rect())
		.string_("Tolerance ")
		.font_(static_font);
		mStaticTextTolerance
		.fixedWidth_(mStaticTextTolerance.sizeHint.width)
		.stringColor_(Color.white)
		.align_(\center);

		mNumberBoxToleranceAmplitude = NumberBox(mViewCSE, Rect())
		.value_(0.2)
		.clipLo_(0)
		.step_(0.1)
		.scroll_step_(0.1);

		mNumberBoxTolerancePhase = NumberBox(mViewCSE, Rect())
		.value_(0.4)
		.clipLo_(0)
		.step_(0.1)
		.scroll_step_(0.1);

		////////////////////////////////////////////////////////////
		////////////////////////////////////////////////////////////

		mStaticTextWindowSize = StaticText(mViewCSE, Rect())
		.string_("Window ")
		.font_(static_font);
		mStaticTextWindowSize
		.fixedWidth_(mStaticTextWindowSize.sizeHint.width)
		.stringColor_(Color.white)
		.align_(\center);

		mNumberBoxWindowSizeAmplitude = NumberBox(mViewCSE, Rect())
		.value_(10)
		.clipLo_(2)
		.step_(1)
		.scroll_step_(1)
		.action_ { | nb |
			// Note that the sequence length cannot be larger than or equal to the window size.
			if (mNumberBoxSequenceLengthAmplitude.value > (nb.value - 1), {
				mNumberBoxSequenceLengthAmplitude.valueAction_( nb.value - 1 );
			});
			mNumberBoxSequenceLengthAmplitude.clipHi_(nb.value - 1);
		};

		mNumberBoxWindowSizePhase = NumberBox(mViewCSE, Rect())
		.value_(10)
		.clipLo_(2)
		.step_(1)
		.scroll_step_(1)
		.action_ { | nb |
			// Note that the sequence length cannot be larger than or equal to the window size.
			if (mNumberBoxSequenceLengthPhase.value > (nb.value - 1), {
				mNumberBoxSequenceLengthPhase.valueAction_( nb.value - 1 );
			});
			mNumberBoxSequenceLengthPhase.clipHi_(nb.value - 1);
		};

		////////////////////////////////////////////////////////////
		////////////////////////////////////////////////////////////

		mStaticTextSequenceLength = StaticText(mViewCSE, Rect())
		.string_("Length ")
		.font_(static_font);
		mStaticTextSequenceLength
		.fixedWidth_(mStaticTextSequenceLength.sizeHint.width)
		.stringColor_(Color.white)
		.align_(\center);

		mNumberBoxSequenceLengthAmplitude = NumberBox(mViewCSE, Rect())
		.value_(1)
		.clipLo_(1)
		.clipHi_(mNumberBoxWindowSizeAmplitude.value - 1)
		.step_(1)
		.scroll_step_(1);

		mNumberBoxSequenceLengthPhase = NumberBox(mViewCSE, Rect())
		.value_(1)
		.clipLo_(1)
		.clipHi_(mNumberBoxWindowSizePhase.value - 1)
		.step_(1)
		.scroll_step_(1);

		////////////////////////////////////////////////////////////
		////////////////////////////////////////////////////////////

		mStaticTextHarmonics = StaticText(mViewCSE, Rect())
		.string_("Harmonics ")
		.font_(static_font);
		mStaticTextHarmonics
		.fixedWidth_(mStaticTextHarmonics.sizeHint.width)
		.stringColor_(Color.white);

		mNumberBoxHarmonicsAmplitude = NumberBox(mViewCSE, Rect())
		.value_(4)
		.clipLo_(1)
		.clipHi_(20) // We don't know how many are actually available.
		.step_(1)
		.scroll_step_(1);

		mNumberBoxHarmonicsPhase = NumberBox(mViewCSE, Rect())
		.value_(4)
		.clipLo_(1)
		.clipHi_(20) // We don't know how many are actually available.
		.step_(1)
		.scroll_step_(1);

		mViewCSE.allChildren do: { | c, i |
			if (c.isKindOf(NumberBox), {
				c.font_(static_font);
				c.fixedWidth_(boxWidth);
				c.fixedHeight_(boxHeight);
			});
			if (c.isKindOf(StaticText), { c.fixedHeight_(boxHeight) });
			if (c.isKindOf(CheckBox),   { c.fixedHeight_(boxHeight) });
		};

		vGap = 1;
		gl2 = GridLayout.rows(
			[
				mStaticTextSampEn,
				mStaticTextAmplitude,
				mStaticTextPhase
			],
			[
				mStaticTextTolerance,
				mNumberBoxToleranceAmplitude,
				mNumberBoxTolerancePhase
			],
			[
				mStaticTextWindowSize,
				mNumberBoxWindowSizeAmplitude,
				mNumberBoxWindowSizePhase
			],
			[
				mStaticTextSequenceLength,
				mNumberBoxSequenceLengthAmplitude,
				mNumberBoxSequenceLengthPhase
			],
			[
				mStaticTextHarmonics,
				mNumberBoxHarmonicsAmplitude,
				mNumberBoxHarmonicsPhase
			],
			[ nil ! 3 ]
		);

		gl2.setAlignment(mStaticTextAmplitude, \center);
		gl2.setAlignment(mStaticTextPhase, \center);
		4 do: { |i| gl2.setAlignment(0@(i+1), \right) };
		gl2.hSpacing_(vGap);
		gl2.vSpacing_(vGap);
		gl2.setRowStretch(5, 3);

		mViewCSE.layout = gl2;

		// Force a grid redraw when any SampEn-related parameter is changed
		mViewCSE.allChildren do: { |v| if (v.class == NumberBox,
			{
				v.addAction( { mScopeViewer.refresh } );
		})
		} ;

		mViewCSE.setProperty(\contextHelp, helpCSEView);
		this.sampEnControlsVisible(false);
	} /* initMenuCSE */

	enableInterface { | enable |
		[
			mNumberBoxToleranceAmplitude,
			mNumberBoxWindowSizeAmplitude,
			mNumberBoxSequenceLengthAmplitude,
			mNumberBoxHarmonicsAmplitude,
			mNumberBoxTolerancePhase,
			mNumberBoxWindowSizePhase,
			mNumberBoxSequenceLengthPhase,
			mNumberBoxHarmonicsPhase
		]
		do: { | ctrl |
			ctrl.enabled_(enable);
		};

		mTableView.numItems do: { | i |
			var item = mTableView.itemAt(i).view(0).enabled_(enable);
		};

		mHeadingFont = VRPViewMain.staticFont.deepCopy;
		mHeadingFont.italic_(true);
		// mbStretchOK = enable;
	}

	sampEnControlsVisible { | b |
		if (b, {
			var rc = Rect(mTableView.absoluteBounds.left+400, mTableView.absoluteBounds.top, 300, 125);
			mViewCSEwindow.setTopLeftBounds(rc);
		});
		mViewCSEwindow.visible_(b);
 	}

	layout { ^mView; }

	stash { | settings |
		var sp = settings.plots;
		// var ss = settings.sampen;

		mNumberBoxToleranceAmplitude.value_(sp.amplitudeTolerance);
		mNumberBoxWindowSizeAmplitude.value_(sp.amplitudeWindowSize);
		mNumberBoxSequenceLengthAmplitude.value_(sp.amplitudeSequenceLength);
		mNumberBoxHarmonicsAmplitude.value_(sp.amplitudeHarmonics);

		mNumberBoxTolerancePhase.value_(sp.phaseTolerance);
		mNumberBoxWindowSizePhase.value_(sp.phaseWindowSize);
		mNumberBoxSequenceLengthPhase.value_(sp.phaseSequenceLength);
		mNumberBoxHarmonicsPhase.value_(sp.phaseHarmonics);

		mTableView.numItems do: { |i|
			mTableView.itemAt(i).view(0).value_(sp.plotMetrics[i+1]);
		};

		mNewDuration = settings.plots.duration;
		mView.setProperty(\visible, sp.isVisible, true);
		mView.refresh;
	} /* stash */

	fetch { | settings |
		var ss, sp;

		if (settings.waitingForStash, {
			this.stash(settings);
		});

		// ss = settings.sampen;
		sp = settings.plots;

		sp.amplitudeTolerance = mNumberBoxToleranceAmplitude.value;
		sp.amplitudeWindowSize = mNumberBoxWindowSizeAmplitude.value;
		sp.amplitudeSequenceLength = mNumberBoxSequenceLengthAmplitude.value;
		sp.amplitudeHarmonics = mNumberBoxHarmonicsAmplitude.value;

		sp.phaseTolerance = mNumberBoxTolerancePhase.value;
		sp.phaseWindowSize = mNumberBoxWindowSizePhase.value;
		sp.phaseSequenceLength = mNumberBoxSequenceLengthPhase.value;
		sp.phaseHarmonics = mNumberBoxHarmonicsPhase.value;
		sp.isVisible = mView.visible;

		///// NEW CONTROLS ///////////
		mTableView.numItems do: { |i|
			sp.plotMetrics.put(i+1, mTableView.itemAt(i).view(0).value);
		};

		mIdleGraphsRequested = sp.graphsRequested;
		mTempDuration = (mNewDuration*mXscale).clip(1,10);
		settings.plots.duration = mNewDuration;
	} /* fetch */

	updateData { | data |
		var duration = mTempDuration;
		var dsg = data.settings.general;
		var dsp = data.settings.plots;
		var scopeData = data.scope.sampen;
		var series;

		this.enableInterface(data.general.started.not);

		if ( duration != mScopeViewer.hspec.range, {
			mScopeViewer.hspec = ControlSpec(duration.neg, 0, units: "s");
		});

		// Build the array of time-series for plotting, and draw them

		// If running, get the data from the buses
		if (scopeData.notNil and: data.general.started,
			{
				series = dsp.graphsRequested collect: { | metricID, i|
					var m = VRPSettings.metrics[metricID];
					scopeData[i+1].linlin(m.plotMin, m.plotMax, 0, 1.0, nil)
					};
				mScopeViewer.update(scopeData.first, series, (data.general.pause == 2));
		});

		// Tell the ScopeViewer which colours we will be using
		if (data.general.starting or: bSignalPlotPending, {
			var c = [];
			mTableView.numItems do: { | i |
				var item = mTableView.itemAt(i);
				var cb = item.view(0);
				if (cb.value, { c = c.add(mCurveColors[i]) });
			};
			mScopeViewer.reset;
			mScopeViewer.colors = c;
		});

		// If not running, check if user wants any metrics plotted
		if (data.general.idle and: (signalMetricsData.notNil), {
			mScopeViewer.hspec = ControlSpec(signalMetricsData.first.first, signalMetricsData.first.last, units: "s");
			if (bSignalPlotPending , {
				series = mIdleGraphsRequested collect: { | metricID, i|
					var m = VRPSettings.metrics[metricID];
					signalMetricsData[i+1].linlin(m.plotMin, m.plotMax, 0, 1.0, nil)
				};
				mScopeViewer.update(signalMetricsData.first, series, true);
				mScopeViewer.refresh;
				bSignalPlotPending = false;
				"done.".postln;
			});
		});

		if (dsg.guiChanged, {
			// Set the theme colors
			mView.background_(dsg.getThemeColor(\backPanel));
			mTableView.background_(dsg.getThemeColor(\backPanel));
			mViewCSE.background_(dsg.getThemeColor(\backPanel));
			mTableView.numItems.do ({ arg i;
				var item = mTableView.itemAt(i);
				var st, cb;
				var textColor = dsg.getThemeColor(\panelText);
				var backColor = dsg.getThemeColor(\backPanel);
				item.colors = backColor ! mTableView.numColumns;
				item.textColors = textColor ! mTableView.numColumns;
				// Custom views need special treatment, for some reason
				// class CheckBox does not implement .stringColor (!!)
				cb = item.view(0);
				if (cb.isKindOf(CheckBox), {
					cb.palette = cb.palette.windowText_(dsg.getThemeColor(\panelText));
					cb.palette = cb.palette.window_(Color.white /* dsg.getThemeColor(\backPanel) */);
				});
			});

			mView.allChildren do: { |v| if (v.class == StaticText,
				{
					v.stringColor = dsg.getThemeColor(\panelText);
				})
			} ;
			mViewCSE.allChildren do: { |v| if (v.class == StaticText,
				{
					v.stringColor = dsg.getThemeColor(\panelText);
				})
			} ;

			mScopeViewer.background_(dsg.getThemeColor(\backGraph));
			mScopeViewer.gridFontColor_(dsg.getThemeColor(\dullText), dsg.getThemeColor(\panelText));
			this.updateGraphOnly;
		});

		if ( data.general.stopping, {
			mScopeViewer.stop;
			mTableView.numItems do: { | i |
				mTableView.itemAt(i).view(0).enabled_(true);
			};
		});

	} /* updateData */

	updateGraphOnly {
		mScopeViewer.refresh;
	}

	update { | menu, who, whatHappened, newValue |
		var r = Routine {
			var cond = Condition.new(false);
			signalMetricsData = this.getLogFileData(newValue, cond);
			cond.wait;
			bSignalPlotPending = true;
		};

		if (whatHappened == \requestMetricsPlot, {
			if (newValue.isNil, {
				signalMetricsData = nil;
				mScopeViewer.reset;
				mScopeViewer.refresh;
			}, {
				AppClock.play(r);
			})
		});
	}

	getLogFileData { arg sigView, cond;
		var startFrame, durationFrames, sfv, rate;
		var c, buf, logTracks, timeData, trackData;
		var jFirst, jLast, nFramesToLoad;
		var firstTime, lastTime;
		var logFrames = nil;
		logTracks = [0];

		if (sigView.isNil, { ^nil });

		"Plotting metrics... ".post;

		// Prevent filling of scheduler queue while we are waiting
		~dialogIsOpen = true;

		sfv = sigView.soundFileView;
		rate = sigView.soundFile.sampleRate.asFloat;
		startFrame = sfv.selectionStart(sigView.class.iSelection);
		durationFrames = sfv.selectionSize(sigView.class.iSelection);
		if ( (durationFrames >= 0), {
			metricTable.do { | m, i |
				if (mTableView.itemAt(i).view(0).value, {
					// Get L1 too, if it's HRFegg
					if (m[0] == \HRFegg, { logTracks = logTracks.add(13) });
					logTracks = logTracks.add(m[6])
				})
			};
		};
		);

		// Most of these steps are performed by the server,
		// so we have to wait for each one to be completed.
		c = Condition.new(false);

		// First load only the time track from the matching logFile
		c.test = false;
		buf = Buffer.readChannel(Server.default, sigView.logPathName,
			startFrame: 0,
			numFrames: -1,
			channels: [0],
			action: { |b| c.test = true; c.signal }
		);
		buf.server.sync(c);

		// Get the entire time track data from the server to the client
		c.test = false;
		buf.loadToFloatArray(action: { arg array;
			timeData = array;
			c.test = true;
			c.signal;
		});
		buf.server.sync(c);

		jFirst = timeData.indexOfGreaterThan(startFrame.asFloat/rate) ? 0;
		jLast  = timeData.indexOfGreaterThan((startFrame.asFloat + durationFrames)/rate) ? (timeData.size - 1);
		nFramesToLoad = jLast - jFirst;

		// Load the relevant tracks from the selected section of the matching logFile
		c.test = false;
		buf = Buffer.readChannel(Server.default, sigView.logPathName,
			startFrame: jFirst,
			numFrames: nFramesToLoad,
			channels: logTracks,
			action: { |b| c.test = true; c.signal }
		);
		buf.server.sync(c);

		// Get the channel data from the server to the client
		c.test = false;
		buf.loadToFloatArray(action: { arg array;
			trackData = array;
			c.test = true;
			c.signal;
		});
		buf.server.sync(c);

		// trackData is now a 1-D array, but we want 2D
		logFrames = trackData.reshape((trackData.size/logTracks.size).asInteger, logTracks.size).flop;

		// The Log file contains no track for the metric HRFegg.
		// However, it can be computed from another track minus track 13.
		// If logTracks includes 13 (L1), then the next track is proto-HRFegg,
		// from which track 13 should be subtracted to yield HRFegg in Bels.
		// Track 13 should then be removed from logFrames
		if (logTracks.includes(13), {
			var subTrack = logTracks.indexOf(13);
			var aLevel1 = logFrames.removeAt(subTrack);
			logFrames[subTrack] = (logFrames[subTrack] - aLevel1) * 10.0;  // to dB
		});

		// Finally, patch the time track's first and last frames
		// to exactly match the selected signal
		// (which might not match the Log file's period markers).
		firstTime = startFrame.asFloat / rate;
		lastTime = (startFrame + durationFrames).asFloat / rate;
		logFrames.first[0] = firstTime;
		logFrames.first[nFramesToLoad-1] = lastTime;

		// Clean up
		buf.close;
		buf.free;
		~dialogIsOpen = false;
		cond.test = true;
		cond.signal;
		^logFrames
	} /* .loadLogData */


	close {
		mViewCSEwindow.close;
	}
}