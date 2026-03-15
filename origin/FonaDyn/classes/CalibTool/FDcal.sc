/* Separate tool for FonaDyn SPL calibration */

// Version 0.5: adapted drawing of grids to SC 3.13.0
// Version 0.4: corrected dB tick positions on some meters
//              and dB readings peak/RMS
// 				and following of VRPViewVRP.nMaxSPL

// Robust storage of global constants
FD_c{
	*version{ ^"0.6" }
	*bDebug{ ^true }
	*nBufSize{ ^1024 }
	*dBFS{ ^120}		// decibels full scale (peak)
} /* FD_c */

FDcal{
	// Views
	var listChooseScenario, buttonNext, buttonPrev, imageView, textInstructions;
	var scope, spectrum, servermeter;
	var containerView, visibleViews;
	classvar <calFont;
	classvar mWindow = nil;
	classvar <nTicks, <nMajorTicks;

	// State variables
	var mScenarioNo, mSteps, mStepNo;

	// Functions
	var reLayout, reSelect;

	// Data arrays
	var steps_A, steps_B, steps_C, steps_D, imageLocation;

	*categories { ^ #["FonaDyn"] }

    *run {
		FDcal.new();
	}

	*new { arg voiceMic=0, refMic=1;
		^super.new.init( voiceMic, refMic )
	}

	gotoScenario { arg nScenario;
		var stepArrays;

		stepArrays = [steps_A, steps_B, steps_C, steps_D ];
		if (nScenario < stepArrays.size,
			{
				mSteps = stepArrays[nScenario];
				mScenarioNo = nScenario
			},{
				"Scenario out of range".error;
			}
		);
		this.gotoStep(0);   // Always restart the sequence for a new scenario
	}

	gotoStep { arg nStep;
		if ((nStep < mSteps.size) and: (nStep >= 0),
			{ mStepNo = nStep }
		);
		buttonPrev.enabled_(nStep > 0);
		buttonNext.enabled_(nStep < (mSteps.size-1));
		buttonNext.visible_(nStep < (mSteps.size-1));
		reSelect.();
		reLayout.();
	}

	init { arg voiceMic, refMic;
		// Prevent more than one instance from running,
		// instead bring the existing one to the front.
		if (mWindow.notNil, {
			mWindow.front;
			^nil
		});

		calFont = Font.new("Arial", 16);
		~refMicInput = refMic;
		~voiceMicInput = voiceMic;
		imageLocation = PathName(FDcal.class.filenameSymbol.asString).pathOnly.tr($\\, $/);
		nTicks = if (VRPDataVRP.nMaxSPL == 140, 21, 17);
		nMajorTicks = if (VRPDataVRP.nMaxSPL == 140, 6, 9);


		steps_A = [
			[ "mic-in-calibrator.jpg", "1. Insert the front mic in the calibrator, and turn on the tone (94 dB).", [], [] ],
			[ "setgain.jpg",    "2. Adjust the mic gain so that the green bar is at 94 dB.", [ FD_audioIn ], ["Mic in calibrator"], [0] ],
			[ "dist30cm-front.jpg",   "3. Stand the mic 0.3 m in front of the subject.", [ FD_audioIn ], ["Calibrated front mic"], [0] ]
		];

		steps_B = [
			[ "speaker-dB-mic.jpg", "1. Connect speaker to 2nd output.\n\tStand the dB meter very near the mic,\nset it to Slow, A-weighting.", [], []  ],
			[ "setgain.jpg", "2. Be quiet. Adjust the mic gain so that the \"Mic level\"\n\tmatches the level shown on the dB meter.",
				[FD_noiseOut, FD_audioIn], ["Noise @ 1 kHz", "Mic level"], [0, 0] ]
		];

		steps_C = [
			[ "mic-in-calibrator.jpg", "1. Connect a reference mic to a spare mic input.\n\tInsert the reference mic in the calibrator,\nand turn on the tone (94 dB).",
				[], [] ],
			[ "setgain.jpg",    "2. Select the spare \"Input\" (first=0).\n\tAdjust the reference mic gain so that the green bar is at 94 dB.",
				[ FD_audioIn ], ["Mic in calibrator"], [1] ],
			[ "dist30cm-headset-ah.jpg",   "3. Detach the calibrator,\nstand the reference mic @ 0.3 m,\nand put the headset on the subject.",
				[ FD_audioIn, FD_audioIn ], ["Calibrated mic", "Headset mic"], [1, 0] ],
			[ "setgain.jpg",   "4. Subject sustains /a/.\nAdjust the headset mic gain\n\tso that the \"Level difference\" sits near zero.",
				[ FD_audioIn, FD_audioIn, FD_audioDiff ], ["Calibrated mic", "Headset mic", "Level difference"], [1,0,2] ],
		];

		steps_D = [
			[ "dist30cm-dbmeter-ah.jpg", "1. Put the headset on the subject.\nStand the dB meter at 0.3 m.\nSet it to Slow, C-weighting.\nNote the ambient noise level.", [], [] ],
			[ "setgain.jpg", "2. Subject sustains /a/, >15 dB above ambient noise level.\nAdjust the mic gain so that the \"Headset mic level\"\nmatches the level shown on the dB meter",
				[FD_audioIn], ["Headset mic level"], [0] ]
		];

		mSteps = steps_A;
		mStepNo = 0;
		format("FonaDyn SPL Calibration Tool v%", FD_c.version).postln;
		Server.default.waitForBoot({
			postln("Server booted.");
			this.createPanel;
			this.compileSynthDefs;
			Server.default.sync;
		});
	}  /* init {} */

	compileSynthDefs {
		// Widget classes must be in this order
		[FD_audioIn, FD_audioIn, FD_audioDiff, FD_noiseOut]
		do: {|c, i| { c.compileSynthDefs(i) }.defer };
	}

	createPanel {
		var selectionView, visibleSelections,
		reButton, scopeView, spectrumView,
		lChooseScenario, image, rc;

		// List of scenarios
		listChooseScenario = PopUpMenu.new(nil, Rect(0, 0, 200, 30));
		listChooseScenario
		.value_(0)
		.allowsReselection_(true)
		.items_([
			"Scenario A: Front mic with calibrator",
			"Scenario B: Front mic, tone & dB meter",
			"Scenario C: Headset & reference mic",
			"Scenario D: Headset & front dB meter"
		])
		.action_({ arg lv;
			this.gotoScenario(lv.value);
			reSelect.();
			reLayout.()
		})
		.minHeight_(30)
		.minWidth_(200);

		// Prev button
		buttonPrev = Button.new(nil, Rect(0, 0, 30, 25));
		buttonPrev
		.states_([["< Previous"]])
		.visible_(true)
		.action_( { this.gotoStep(mStepNo-1) } )
		.minHeight_(30)
		.enabled_(false);

		// Next button
		buttonNext = Button.new(nil, Rect(0, 0, 30, 25));
		buttonNext
		.states_([["Next >"]])
		.visible_(true)
		.action_( { this.gotoStep(mStepNo+1) } )
		.minHeight_(30)
		.enabled_(false);

		// Photo frame
		imageView = UserView()
		.backColor_(Color.white)
		.visible_(true);

		// Text area
		textInstructions = StaticText(bounds: Rect(0, 0, 400, 70))
		.backColor_(Color.yellow(0.9))
		.font_(Font.new("Arial", 12))
		.align_(\center)
		.visible_(true);

		// Define a function that sets the layout of the container view
		reLayout = {
			var instructionText;
			var visibleWidgets = mSteps[mStepNo][2];
			var numIns  = Server.default.options.numInputBusChannels;
			var numOuts = Server.default.options.numOutputBusChannels;
			var metersView, scaleView;
			var rc, myWidth = 24;
			var topStr;

			// Hack into the ServerMeterView class to get what I want
			// - see also the class extension at the end of this file.
			ServerMeterView.meterWidth_(20);
			metersView = ServerMeterView.new(Server.default, nil, 10@40, numIns, numOuts);
			metersView.view.minWidth_(ServerMeterView.getWidth(numIns, numOuts, Server.default));

			// Lots of fiddling to paint over the default dB scale...
			topStr = format("%\n[dB]", VRPDataVRP.nMaxSPL);
			rc = metersView.view.bounds.moveTo(10, 20);
			rc.width_(myWidth);
			scaleView = UserView(metersView.view, rc).drawFunc_({
					Pen.color = Color.yellow(0.8);
					Pen.fillRect(Rect(0, 0, myWidth, 30));
					Pen.fillRect(Rect(0, 175, myWidth, 12));
					try {
						Pen.color = \QPalette.asClass.new.windowText;
					} {
						Pen.color = Color.white;
					};
					Pen.font = Font.sansSerif(10).boldVariant;
					Pen.stringInRect(topStr, Rect(0, 0, myWidth, 30));
					Pen.stringCenteredIn("40", Rect(0, 175, myWidth, 12));
			});

			visibleViews = [];
			if (visibleWidgets.size > 0, {
				metersView.stop;
				visibleWidgets.do({| vClass, i |
					var a;
					a = vClass.new(this, mSteps[mStepNo][3][i], mSteps[mStepNo][4][i]);
					visibleViews = visibleViews.add(a.view);
				})
			} , {
				var inNo = 0;
				metersView.view.allChildren do: { | ch, i |
					if ((ch.class == LevelIndicator) and: (inNo < numIns), {
						ch.meterColor_(Color.hsv(inNo/numIns, 1, 1));
						ch.numTicks_(nTicks);
						ch.numMajorTicks_(nMajorTicks);
						inNo = inNo + 1;
					})
				};
				visibleViews = visibleViews.add(metersView.view);
				metersView.start;
			});

			// Remove all existing children views and make them unusable
			containerView.removeAll;

			instructionText = StaticText.new(containerView, Rect());
			instructionText.string =
			"Choose a scenario (Handbook, section 3.3).\nFollow the figure caption, then press Next. Repeat while there is a Next.";
			instructionText
			.align_(\right)
			.maxHeight_(45);

			containerView.layout = VLayout.new(
				[instructionText, stretch: 0],
				5,
				[HLayout.new(*visibleViews), stretch: 4]
			);
			containerView.refresh;
		};

		// Define a function that sets the contents of the selection views
		reSelect = {
			var imageName = mSteps[mStepNo][0];
			var text = mSteps[mStepNo][1];
			var image = Image.open(imageLocation +/+ imageName);

			if (Main.scVersionTweak.notEmpty, {
				// SC 3.14.0-rc1
				var rcSrc;
				var rcDest = imageView.bounds.moveTo(0, 0);
				rcSrc = Rect(0, 0, image.width, image.height);
				imageView.drawFunc_({ | uv | image.drawInRect(rcDest, rcSrc) });
			}, {
				// Does not work in SC 3.14.0-rc1,
				// but is supposedly fixed again in 3.14.0 (#6936, #6970)
				imageView.setBackgroundImage(image, 10);
			});

			textInstructions.string_(text);
			selectionView.refresh;
		};

		// View that contains the scenario controls, photo and instructions
		selectionView = View.new;
		selectionView.layout = VLayout(
			[HLayout([listChooseScenario], 23, [buttonPrev, align: \left], [buttonNext, align: \left]), align:\top, stretch: 0],
			[imageView, stretch: 3],
			[textInstructions, stretch: 1]
		);
		selectionView.layout.margins_(0);
		selectionView.maxSize = Size.new(600, 500);
		selectionView.minSize = Size.new(430, 300);
		// reSelect.();

		// View that contains the level meter(s)
		containerView = View.new(nil, Rect(0, 0, 200, 300));
		containerView.backColor_(Color.yellow(0.8));

		// Main window
		rc = Window.availableBounds().insetBy(100,100);
		rc.width = 750;
		rc.height = 700;
		mWindow = Window.new(
			format("FonaDyn SPL Calibration Tool v%", FD_c.version), rc)
		.front;

		// Offer some keyboard shortcuts
		mWindow.view.keyDownAction_({ |view, char, mod, unicode, keycode, key|
			var bHandled = true;
			case
			{ "ABCD".containsi(char.asString)} {
				listChooseScenario.valueAction_(char.toUpper.asInteger - $A.asInteger);
			}
			{ char.toUpper == $N} { buttonNext.doAction }
			{ char.toUpper == $P} { buttonPrev.doAction }
			{ key == 0x01000014 } { buttonNext.doAction }	// right arrow
			{ key == 0x01000012 } { buttonPrev.doAction }	// left arrow
			{ key == 0x01000000 } { mWindow.close() }	    // ESC to close
			{ bHandled = false };
			bHandled
		});

		// Create and layout the rest
		scope = FD_scope.new();
		scopeView = scope.view;

		spectrum = FD_spectrum.new();
		spectrumView = spectrum.view;

		scope.addUniqueMethod(\firstBusChanged, { spectrum.setBus(scope.scope.index)} );

		mWindow.layout = VLayout.new(
			[ HLayout.new([containerView, stretch:4], [selectionView, stretch:1]).margins_(5), stretch: 1],
			[ HLayout.new([scopeView, stretch: 2], [spectrumView, stretch: 3]).margins_(0), stretch: 3]
		);
		mWindow.layout.margins_(3);

		// spectrum.run(true);

		mWindow.onClose_({ // don't forget this
			spectrum.run(false);
			scope.removeUniqueMethod(\firstBusChanged);
			scope.free;
			mWindow = nil;
		});

		this.gotoScenario(0);
		if (Main.scVersionTweak.notEmpty, { AppClock.sched(0.1, { listChooseScenario.valueAction_(0)}) });
	} /* FDcal.createPanel */

	trigBus {
		^scope.trigBus;
	}

} /* FDcal */

FD_scope{
	var <view, <scope, scopeBus, <trigBus, scopeBuf, synth;

	*new {|... args|
		^super.new.init(*args);
	}

	init {
		view = View.new;
		scopeBuf = Buffer.alloc(Server.default, FD_c.nBufSize, 2);
		scopeBus = Bus.audio(Server.default, 3);  // left, right, trig
		trigBus  = Bus.newFrom(scopeBus, 2, 1);   // for easier access to trig bus
		this.compileSynthDefs;
		this.createPanel;
	}

	compileSynthDefs {
		// Triggers a periodic (?) signal, for scoping using Dolansky
		// Two-signal input, triggered by the first, or by the trig channel
		// Triggers a periodic (?) signal, for scoping
		// Works best with bufsize <= 1024
		SynthDef(\FDscope2, {
			arg busIn = ~voiceMicInput, busOut = 0, tau = 0.995, trigSelect = 0, bufSize = 1024;
			var lBuffer, input, signal, trig, aligned, z, phi, pulse_dur;

			lBuffer = LocalBuf(bufSize, 2);
			pulse_dur = bufSize/Server.default.sampleRate;
			// Get signals from given buses
			input = In.ar(busIn, 1) * 0.7071;
			// Cycle detection.
			z = Trig1.ar(Dolansky.ar(input, 0.999, 0.99), pulse_dur);
			// Construct a phase phi for BufWr
			phi = Phasor.ar(z, 1, 0, 2*bufSize, 0).clip2(bufSize);
			// Start writing into lBuffer on the z trigger
			BufWr.ar(input, lBuffer, phi, 0);
			// PlayBuf seems to work
			aligned = PlayBuf.ar(2, lBuffer, rate: 1, trigger: 1, startPos: 0, loop: 1);
			// ReplaceOut.ar(busOut, aligned);
			OffsetOut.ar(busOut, aligned);
		}).send(Server.default);

		Server.default.sync;
	}

	createPanel {
		var button, trigButton, scopeIx;
		var firstIn = Server.local.options.numOutputBusChannels;
		var numIns  = Server.local.options.numInputBusChannels;
		var inputColors = numIns collect: { |c| Color.hsv(c/numIns, 1, 1)};
		var fnSetColors;

		scopeIx = firstIn;
		scope = Stethoscope.new(
			Server.default,
			numChannels: numIns,
			index: scopeIx,
			bufsize: FD_c.nBufSize,
			view: view);
		scope.scopeView.fill_(false);
		scope.stop;

		// Colour the channels according to input-#,
		// else white (outputs) or gray (internal buses)
		fnSetColors = { arg scopeIndex, scopeChannels;
			Array.fill(scopeChannels, { |c|
				var busNo = scopeIndex + c;
				case
				{ busNo < firstIn }            { Color.white }
				{ busNo < (firstIn + numIns) } { inputColors[busNo-firstIn] }
				{ busNo >= (firstIn + numIns)} { Color.gray };
			})
		};

		// Recolour when either of .index or .numChannels is changed by the user
		scope.view.children do: { | ch |
			if (ch.class == NumberBox,
				{
					ch.addAction( {
						scope.scopeView.waveColors = fnSetColors.(scope.index, scope.numChannels);
						this.firstBusChanged.();
					} )
				}
			)
		};

		// Add a button to start and stop the displays.
		button = Button(view, 40 @ 20);
		button.states = [["Scope on", Color.black, Color.green],["Scope off", Color.white, Color.red]];
		button.action = {|view|
			if (view.value == 1) {
				synth = Synth.new(\FDscope2,
					[\busIn, scopeIx, \busOut, scopeBus, \bufSize, FD_c.nBufSize],
					addAction: \addToTail);
				scope.scopeView.waveColors = fnSetColors.(scope.index, scope.numChannels);
				trigButton.visible_(true);
				scope.run;
			};
			if (view.value == 0) {
				synth.free;
				trigButton.visible_(false);
				scope.stop;
			};
		};

		// A button to select the trig source
		trigButton = Button(view, 40 @ 20);
		trigButton.states = [
			["No trig", Color.black, Color.gray],
			["Trig on Voice", Color.white, Color.gray]
			// ["Trig on Ref", Color.red, Color.gray]
		];
		trigButton.action = {arg b;
			if (b.value == 0, {
				scope.index = Server.local.options.numOutputBusChannels;
				scope.numChannels = numIns;
				scope.scopeView.waveColors = fnSetColors.(scope.index, scope.numChannels);
			} , {
				scope.index = scopeBus.index;
				scope.numChannels = 1;
			});
		};

		view.onClose = { // don't forget this
			scope.quit;
			synth.free;
			trigBus.free;
			scopeBus.free;
			scopeBuf.free;
		};

		view.layout = VLayout.new([scope.view, s: 5],
			HLayout.new([button, s: 0, a: \left ], [trigButton, s: 0, a: \left], nil));
		view.layout.spacing_(2);
		view.layout.margins_(3);

		// Now start the scope
		button.valueAction = 1;
	} /* FD_scope.createPanel */

	extTrig { arg t;
		synth.set(\trigSelect, t);
	}

} /* FD_scope */


FD_spectrum{
	var mGridFreq, mGridLevel;
	var <view, fsv, button, button2, nyquist;

	// this is a normal constructor method
	*new {  // * indicates this is a class method
		^super.new.init()
	}

	init {
		this.createPanel;
	}

	setBus { | index |
		fsv.inBus = index;
	}

	createPanel {
		var d, dy, dBSpec, freqSpec, fScaler, gridY, sView, lView;

		view = View.new;
		view.resize_(5);
		view.minSize_(250@200);

		fsv = FreqScopeView(view, view.bounds);
		fsv.resize_(5);
		fsv.scope.waveColors_([Color.yellow]);
		fsv.dbRange_(VRPDataVRP.nMaxSPL - 20);
		fsv.specialSynthArgs_([\fftBufSize, 2048]);
		fsv.inBus = ~voiceMicInput + Server.default.options.numOutputBusChannels;

		// why does Server.options.sampleRate return nil?
		nyquist = Server.default.actualSampleRate/2;
		freqSpec = ControlSpec(0, nyquist, \lin, 1, 200, "Hz");
		// Full scale SPL follows that in FonaDyn
		dBSpec = ControlSpec(VRPDataVRP.nMaxSPL - fsv.dbRange, VRPDataVRP.nMaxSPL, \lin, 1, -10, "dB");

		// Level scale
		gridY = GridLines.new(dBSpec);
		lView = UserView(view, Rect(0, 0, 35, view.bounds.height));
		lView.fixedWidth = 35;
		lView.resize_(4);
		lView.background = Color.new(0.2, 0.2, 0.2);

		// Frequency scale
		mGridFreq = GridLines.new(freqSpec);
		sView = UserView(view, Rect(0, 0, view.bounds.width, 15));
		sView.fixedHeight = 15;
		sView.resize_(8);
		sView.background = Color.new(0.2, 0.2, 0.2);

		// Run/freeze button
		button = Button.new(view, 40@20);
		button.states = [["Run", Color.black, Color.green], ["Freeze", Color.white, Color.red]];
		button.action = {|b| this.run(b.value == 1) };

		// Lin/log button
		button2 = Button.new(view, 40@20);
		button2.states = [["Lin", Color.black, Color.gray], ["Log", Color.white, Color.gray]];
		button2.action = { arg b;
			fsv.freqMode_(b.value);
			if (b.value == 0)
				{
				freqSpec = ControlSpec(0, nyquist, \lin, 1, 200, "Hz");
				mGridFreq = GridLines.new(freqSpec);
				}
				{
				freqSpec = ControlSpec(20, nyquist, \exp, 1, 200, "Hz");
				mGridFreq = GridLines.new(freqSpec);
				};
			d.horzGrid_(mGridFreq);
			if (Main.versionAtLeast(3,13), {
				d.x.labelsShowUnits_(true)
			});
			sView.refresh;
		};

		// dB axis
		dy = DrawGrid.new(lView.bounds, nil, gridY);
		dy.fontColor_(Color.white);
		dy.gridColors_([Color.white, Color.white]);
		if (Main.versionAtLeast(3,13), {
			dy.y.labelAnchor_(\top)
			.tickSpacing_(50, 20)
			.labelAlign_(\right)
			.labelOffset_(18@1)
			.labelsShowUnits_(true)
			.drawBoundingRect_(false);
		});
		lView.drawFunc = { arg v; dy.bounds = v.bounds.moveTo(0, 0) ; dy.draw; };

		// Frequency axis
		d = DrawGrid.new(sView.bounds, mGridFreq, nil);
		d.horzGrid_(mGridFreq);
		d.fontColor_(Color.white);
		d.gridColors_([Color.white, Color.white]);
		if (Main.versionAtLeast(3,13), {
			d.x.labelAnchor_(\bottom)
			.tickSpacing_(50, 20)
			.labelAlign_(\left)
			.labelOffset_(24@1)
			.labelsShowUnits_(true)
			.drawBoundingRect_(false);
		});
		sView.drawFunc = { arg v; d.bounds = v.bounds.moveTo(0,-4); d.draw; };

		// Frequency scaler (1...10x)
		// There is a bug in FreqScopeView that disables zooming below a certain window width
		fScaler = Slider(view, 60@20);
		fScaler.value = 0;
		fScaler.action_({|f|
			var zoomX = 1.0 + (9.0*f.value);
			freqSpec.maxval = nyquist/zoomX;
			if (freqSpec.warp.class == LinearWarp, {
				freqSpec.minval = 0.0;
			},{
				freqSpec.minval = 20.0;
				zoomX = (log10(nyquist)-log10(freqSpec.minval))/(log10(freqSpec.maxval)-log10(freqSpec.minval));
			});
			fsv.scope.xZoom_(zoomX);
			mGridFreq.spec = freqSpec;
			d.horzGrid_(mGridFreq);
			sView.refresh;
		});

		view.layout = VLayout(
			HLayout([lView, s: 0], [fsv.asView, stretch: 2]),
			HLayout([36, s: 0], [sView, s: 2]),
			HLayout([36, s: 0], [button, s: 0, a: \left], [button2, s: 0, a: \left], [fScaler, s:0], [nil, s: 2])
		);
		view.layout.spacing_(2);
		view.layout.margins_(4);
		view.onClose_({ fsv.kill; });

		// Now start the analyzer
		button.valueAction = 1;
	}

	run { arg bRun;
		fsv.active_(bRun);
		button2.visible_(bRun == false);
	}

} /* FD_spectrum */


FD_audioIn{
	var <view, audioOuts, audioIns, <inputBus, strLabel, micID;

	*new { arg main, label, mic;
		^super.new.init(main, label, mic)
	}

	init { arg main, label, mic;
		audioOuts = Server.local.options.numOutputBusChannels;
		audioIns  = Server.local.options.numInputBusChannels;
		inputBus = audioOuts;  /* index of first input, by default */
		switch (mic,
			0, { inputBus = audioOuts + ~voiceMicInput },
			1, { inputBus = audioOuts + ~refMicInput }
		);
		// this.compileSynthDefs;   ALREADY DONE
		strLabel = label;
		micID = mic;

		this.createPanel;
	}

	*compileSynthDefs { arg mic;
		var sdSymbol = ("FDaudioIn"++mic).asSymbol;
		SynthDef(sdSymbol, {
			arg inBus = 0, outBus = 0;
			var imp, delimp, signal;

			signal = HPF.ar(In.ar(inBus, 1), 30); // HPF +12 db/oct to reduce rumble, same as in FonaDyn

			// Uncomment to record SPL calibration (risk for feedback)
			// Out.ar(outBus, signal);

			imp = Impulse.kr(4);
			delimp = Delay1.kr(imp);
			// measure rms and Peak
			SendReply.kr(imp, ("/level"++mic).asSymbol, [RMS.ar(signal, 1), K2A.ar(Peak.ar(signal, delimp).lag(0, 3))]);
		};
		).send(Server.default)
	}  /* compileSynthDefs() */

	createPanel {
		var l, c, d, synth;
		var dBmeter, oscFunc;
		var sdSymbol = ("FDaudioIn"++micID).asSymbol;

		view = CompositeView.new();
		view.minSize = Size.new(70, 30);
		view.background = Color.hsv(1 / 8.0, 0.1, 1);
		view.onClose_({ synth.free; this.free });
		view.decorator = FlowLayout(view.bounds, 5@5, 5@5);

		l = StaticText(view, Rect(5, 5, 100, 15))
		.string = strLabel;

		c = EZNumber.new(view, Rect(5, 30, 70, 25), "Input",
			ControlSpec(0, audioIns-1, 'lin', 1, { switch (micID,
					0, { ~voiceMicInput },
					1, { ~refMicInput }
			)}), { |ez|
				inputBus = ez.value + audioOuts;
				synth.set(\inBus, inputBus);
				switch (micID,
					0, { ~voiceMicInput = ez.value },
					1, { ~refMicInput = ez.value }
				)
			},
			inputBus-audioOuts, true, 40, 30);
		c.setColors(stringColor: Color.black, numBackground: Color.green);
		c.font = FDcal.calFont;

		d = StaticText(view, Rect(5, 0, 70, 15))
		.string_("-- dB")
		.font_(FDcal.calFont)
		.align_(\center);

		dBmeter = LevelIndicator.new(view, Rect(0, 0, 70, 140));
		dBmeter
		.style_(\continuous)
		.drawsPeak_(true)
		.numTicks_(FDcal.nTicks)
		.numMajorTicks_(FDcal.nMajorTicks);
		dBmeter.warning  = 0.90;
		dBmeter.critical = 0.98;

		oscFunc = OSCFunc({arg msg;
			{
				dBmeter.value = msg[3].ampdb.linlin(40 - VRPDataVRP.nMaxSPL, 0, 0, 1);
				dBmeter.peakLevel = msg[4].ampdb.linlin(40 - VRPDataVRP.nMaxSPL, 0, 0, 1);
				d.string_(format("% dB", msg[3].ampdb.round(0.1) + VRPDataVRP.nMaxSPL));
			}.defer;
		}, ("/level"++micID).asSymbol, Server.default.addr);

		synth = Synth.new(sdSymbol, [\inBus, inputBus], addAction: \addToHead);
	} /* createPanel */

} /* FD_audioIn */



FD_audioDiff{
	var <view, audioOuts, audioIns, <inputBus, strLabel, micID;

	*new { arg main, label, mic;
		^super.new.init(main, label, mic)
	}

	init { arg main, label, mic;
		audioOuts = Server.local.options.numOutputBusChannels;
		audioIns  = Server.local.options.numInputBusChannels;
		inputBus = audioOuts;  /* index of first input, by default */
		// this.compileSynthDefs;  ALREADY DONE
		strLabel = label;
		micID = mic;

		this.createPanel;
	}

	*compileSynthDefs { arg mic;
		SynthDef(\FD_leveldiff, {
			arg inBus1 = ~refMicInput, inBus2 = ~voiceMicInput;
			var imp, delimp, ref, head, signal;

			ref  = RMS.ar(In.ar(inBus1, 1), 4);
			head = RMS.ar(In.ar(inBus2, 1), 4);
			signal = head / ref;

			imp = Impulse.kr(4);
			delimp = Delay1.kr(imp);
			// measure rms and Peak
			SendReply.kr(imp, ("/level"++mic).asSymbol, [RMS.ar(signal, 10), K2A.ar(Peak.ar(signal, delimp).lag(0, 3))]);
		};
		).send(Server.default)

	}  /* compileSynthDefs() */

	createPanel {
		var lA, lB, c, d, synth;
		var dBmeter, oscFunc;

		view = CompositeView.new();
		view.minSize = Size.new(70, 30);
		view.background = Color.hsv(1 / 8.0, 0.1, 1);
		view.onClose_({ synth.free; this.free });
		view.decorator = FlowLayout(view.bounds, 5@5, 5@5);

		lA = StaticText(view, Rect(5,  5, 100, 15))
		.string_(strLabel);

		lB = StaticText(view, Rect(5, 25, 100, 15))
		.string_("(green ±0.5dB)");

		d = StaticText(view, Rect(5, 80, 70, 25))
		.string_("-- dB")
		.font_(FDcal.calFont)
		.align_(\bottom);

		dBmeter = LevelIndicator.new(view, Rect(0, 0, 70, 140));
		dBmeter
		.style_(\continuous)
		.drawsPeak_(false)
		.numTicks_(5);
		dBmeter
		.warning_(0.485)
		.critical_(0.515)
		.meterColor_(Color.yellow)
		.warningColor_(Color.green)
		.criticalColor_(Color.yellow);


		oscFunc = OSCFunc({arg msg;
			{
				dBmeter.value = msg[3].ampdb.linlin(-20, 20, 0, 1);
				dBmeter.peakLevel = msg[4].ampdb.linlin(-20, 20, 0, 1);
				d.string_(format("% dB", msg[3].ampdb.round(0.1)));
			}.defer;
		}, ("/level"++micID).asSymbol, Server.default.addr);

		synth = Synth.new(\FD_leveldiff,
			[\inBus1, audioOuts+~refMicInput, \inBus2, audioOuts+~voiceMicInput],
			addAction: \addToTail
		);
	} /* createPanel */

} /* FD_audioDiff */


FD_noiseOut{
	var <view, audioOuts, strLabel, <outBus;

	*new { arg main, label;
		^super.new.init(main, label)
	}

	init { arg main, label;
		audioOuts = Server.local.options.numOutputBusChannels;
		strLabel = label;
		outBus = 1;
		this.createPanel;
	}

	*compileSynthDefs {
		SynthDef(\FDnoiseOut, { arg outBus=1, toneGain=0.3;
			var wn, calNoise, outNoise;

			calNoise = BPF.ar(WhiteNoise.ar(1), 1000, 0.2, toneGain);
			Out.ar(outBus, [calNoise]);
		};
		).send(Server.default)
	}  /* compileSynthDefs() */

	createPanel {
		var l, c, d, synth, gainKnob;

		view = CompositeView.new();
		view.minSize = Size.new(70, 30);
		view.background = Color.hsv(1 / 8.0, 0.1, 1);
		view.onClose_({ synth.free; this.free });
		view.decorator = FlowLayout(view.bounds, 5@5, 5@5);

		l = StaticText(view, Rect(5, 5, 100, 20))
		.string_(strLabel);

		c = EZNumber(view, Rect(5, 30, 80, 20), "Output",
			ControlSpec(0, audioOuts-1, 'lin', 1, 1),{ |ez|
				outBus = ez.value;
				synth.set(\outBus, outBus);
		}, outBus, false, 40, 30);
		c
		.setColors(stringColor: Color.black, numBackground: Color.green)
		.font_(FDcal.calFont);


		d = StaticText(view, Rect(20, 50, 100, 20))
		.string_("Volume")
		.font_(FDcal.calFont);

		gainKnob = Knob.new(view, Rect(12, 70, 50, 50));
		gainKnob
		.value_(0.3)
		.color_([Color.blue(0.6), Color.blue(0.9), Color.black, Color.gray;])
		.action_( { |k| synth.set(\toneGain, k.value) } );

		synth = Synth.new(\FDnoiseOut, [\outBus, outBus, \toneGain, gainKnob.value], addAction: \addToHead);
	} /* createPanel */

} /* FD_noiseOut */


+ ServerMeterView {
	*meterWidth_{ arg w;
		meterWidth = w;
	}
}

