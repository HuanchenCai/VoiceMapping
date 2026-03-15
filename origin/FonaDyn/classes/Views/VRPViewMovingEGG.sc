// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

VRPViewMovingEGG {
	var mView;

	var mButtonNormalize;
	var mbNormalize;
	var mStaticTextCount;
	var mNumberBoxCount;
	var mStaticTextSamples;
	var mNumberBoxSamples;
	var mCheckValidateEGG;
	var mUV, mUV2;
	var mDMEGG;
	var mCheckThresholdNoise, mNumberBoxThreshold;
	var bThresholdChanged;
	var mScopePenColor;
	var strokeCount;

	var >haveFloated;
	var mWinMovingEGGclone;

	const mMovEggTitle = "Live normalized EGG waveform";


	//// Multi-line context-help texts  //////////////

	var helpNormalize =
"When On, this display normalizes the EGG cycle amplitude.
The EGG cycle duration is always normalized in this graph.
Set this to Off to check the incoming EGG signal for recording.";

	var helpThresholdWhat =
"Signals from EGG hardware are often noisy.
Checking this box invokes a signal suppression
below the given spectral threshold.
-86 (dBFS) is a good default value.
(Handbook section 3.7.1)";

	var helpThresholdHow =
"To find the right value, go to Settings and enable \"Play EGG...\".
Set this value to non-zero, then START the analysis
and listen to the EGG (right-hand) channel.
Adjust this noise threshold so that the noise is as low as possible
without visibly or audibly changing the waveform of the EGG.

While creating a Log file, this number cannot be changed.";

	var helpActivity =
"When checked, mapping happens only if there is EGG activity.
While the participant is quiet, you can talk without being mapped yourself.
This can also be helpful if there is some ambient sound in the room.
This box turns bright green when there is EGG activity.

If you do not have an EGG device, leave this box unchecked.";

	var helpGraph =
"Shows the EGG cycle waveform in real time.

Press Alt+Shift+M to make (or remove)
a floating copy of this graph.";


	//////////////////////////////////////////////////

	*new { | view |
		^super.new.init(view);
	}

	init { | view |
		var static_font = VRPViewMain.staticFont;
		var bold_font = Font.new(\Arial, 8, true, false, true);
		var myLayout;

		mView = view;
		mView.setProperty(\contextHelp, helpGraph);
		haveFloated = 0;

		mbNormalize = true;
		mScopePenColor = Color.gray(0.2);

		mButtonNormalize = Button(mView, Rect())
		.font_(VRPViewMain.qtFont)
		.states_([
			["Normalize: Off"],
			["Normalize: On "]
		])
		.action_({ | v | this.changed(this, \normalization, v.value.asBoolean) })
		.value_(1);
		mButtonNormalize.setProperty(\contextHelp, helpNormalize);

		this addDependant: VRPViewCluster.mAdapterUpdate;
		bThresholdChanged = true;

		///////////////////////////////////////////////////////////////
		///////////////////////////////////////////////////////////////

		mCheckThresholdNoise = CheckBox(mView, Rect())
		.string_("De-noise")
		.font_(static_font)
		.action_({ | cb | mNumberBoxThreshold.visible_( cb.value ); bThresholdChanged = true })
		.value_(true);
		mCheckThresholdNoise
		.fixedWidth_(mCheckThresholdNoise.sizeHint.width)
		.fixedHeight_(35);
		mCheckThresholdNoise.setProperty(\contextHelp, helpThresholdWhat);


		mNumberBoxThreshold = NumberBox(mView, Rect())
		.font_(static_font)
		.value_(-80.0)		// set default value here
		.clipLo_(-120.0)
		.clipHi_(-50.0)
		.step_(1)
		.align_(\right)
		.scroll_step_(1)
		.action_({ bThresholdChanged = true })
		.visible_(true)
		.fixedWidth_(35);

		mNumberBoxThreshold.setProperty(\contextHelp, helpThresholdHow);

		///////////////////////////////////////////////////////////////
		///////////////////////////////////////////////////////////////

		mStaticTextCount = StaticText(mView, Rect())
		.string_("Cycles:")
		.font_(static_font);
		mStaticTextCount
		.fixedWidth_(mStaticTextCount.sizeHint.width)
		.fixedHeight_(35)
		.stringColor_(Color.white);
		mStaticTextCount.setProperty(\contextHelp, "The number of EGG cycles to draw, with fading.");


		mNumberBoxCount = NumberBox(mView, Rect())
		.font_(static_font)
		.value_(5)
		.clipLo_(1)
		.clipHi_(50)
		.step_(1)
		.scroll_step_(1)
		.fixedWidth_(30);
		mNumberBoxCount.setProperty(\contextHelp, "The number of EGG cycle shapes to draw on top of each other.");

		strokeCount = mNumberBoxCount.value;

		///////////////////////////////////////////////////////////////
		///////////////////////////////////////////////////////////////

		mStaticTextSamples = StaticText(mView, Rect())
		.string_("Segments:")
		.font_(static_font);
		mStaticTextSamples
		.fixedWidth_(mStaticTextSamples.sizeHint.width)
		.fixedHeight_(35)
		.stringColor_(Color.white);
		mStaticTextSamples.setProperty(\contextHelp, "The number of line segments drawn per EGG cycle.");

		mNumberBoxSamples = NumberBox(mView, Rect())
		.font_(static_font)
		.value_(80)
		.clipLo_(1)
		.clipHi_(200)
		.step_(1)
		.scroll_step_(1)
		.fixedWidth_(30);
		mNumberBoxSamples.setProperty(\contextHelp, "The number of line segments drawn per EGG cycle.");

		mCheckValidateEGG = CheckBox(mView, Rect(), "Voicing")
		.font_(static_font)
		.value_(false);
		mCheckValidateEGG.setProperty(\contextHelp, helpActivity);

		mUV = UserView(mView, Rect())
		.background_(Color.white)
		.drawFunc_{
			if (mDMEGG.notNil, {
				mDMEGG.setCount(strokeCount);
				mDMEGG.draw(mUV);
			});
		};

		mView.layout_(
			VLayout([
				HLayout(
					[mButtonNormalize, stretch: 1],
					[mStaticTextCount, stretch: 1],
					[mNumberBoxCount, stretch: 1],
					[mStaticTextSamples, stretch: 1],
					[mNumberBoxSamples, stretch: 1],
					[nil, stretch: 8],
					[mNumberBoxThreshold, stretch: 1, align: \right],
					[mCheckThresholdNoise, stretch: 1, align: \right],
					[mCheckValidateEGG, stretch: 1, align: \right]
			), stretch: 0],
			[mUV, stretch: 8]
		));
		mView.layout.margins_(5);
	}

	// Toggle the existence of a floating clone,
	// placing it right on top of the MovingEGG graph
	cloneFloat {
		if (haveFloated == 0, {
			// No floating MovingEGG now, so create it
			var ar = mView.absoluteBounds;
			mWinMovingEGGclone = Window.new(mMovEggTitle);
			mWinMovingEGGclone.setTopLeftBounds(Rect(ar.left, ar.top, ar.width, ar.height-45));

			mUV2 = UserView(
				mWinMovingEGGclone,
				mWinMovingEGGclone.bounds.moveTo(0, 0).insetAll(5, 5, 5, 5)
			).resize_(5)
			.background_(Color.white)
			.drawFunc_{ | uv |
				var b = uv.bounds;
				uv.bounds = b;
				if (mDMEGG.notNil, {
					mDMEGG.setCount(strokeCount);
					mDMEGG.draw(mUV2);
				});
			};

			mUV2.keyDownAction_({ arg v, c, mods, u, kCode, k;
				// Let the user close also with ESC or Alt+Shift+M
				var bHandled = false;
				if ((k == 0x01000000)
					or: ((c.toLower == $m) and: (mods.isShift and: mods.isAlt)),
					{
						mWinMovingEGGclone.close;
					}, { bHandled = true }
				);
				bHandled
			});

			mWinMovingEGGclone.onClose_{ this.haveFloated_(0) };
			mWinMovingEGGclone.front;
			haveFloated = 2;  // This tells .updateData to set the colors for the new window
		}, {
			mWinMovingEGGclone.close;
		});
	}

	stash { | settings |
		var ss = settings.scope;
		mButtonNormalize.value_(ss.normalize);
		mNumberBoxCount.value_(ss.movingEGGCount);
		mNumberBoxSamples.value_(ss.movingEGGSamples);
		mCheckThresholdNoise.valueAction_(ss.denoise);
		mNumberBoxThreshold.valueAction_(ss.noiseThreshold);
		mCheckValidateEGG.value_(ss.validate);
		mView.setProperty(\visible, ss.isVisible, true);
		this.changed(this, \normalization, ss.normalize);
	}

	fetch { | settings |
		var ss = settings.scope;

		if (settings.waitingForStash, {
			this.stash(settings);
		});

		ss.normalize = mButtonNormalize.value;
		mbNormalize = mButtonNormalize.value.asBoolean;
		ss.movingEGGCount = mNumberBoxCount.value;
		ss.movingEGGSamples = mNumberBoxSamples.value;
		ss.isVisible = (mView.visible);
		ss.denoise = mCheckThresholdNoise.value;
		ss.noiseThreshold = mNumberBoxThreshold.value;
		ss.validate = mCheckValidateEGG.value;
	}

	thresholdBusValue { | dBthresh |
		var retval;
		if (mCheckThresholdNoise.value,
			{
				retval = dBthresh.linexp(-120, -50, 0.007, 7);
			}, {
				retval = 0;
			}
		);
		^retval
	}

	updateData { | data |
		var sd = data.scope;
		var gd = data.general;
		var s = data.settings;
		var dsg = data.settings.general;
		var ss = s.scope;
		var bEnabled;

		if (gd.starting, {
			if (mDMEGG.isNil, {
				mDMEGG = DrawableMovingEGG(ss.movingEGGCount, ss.movingEGGSamples, ss.normalize);
			});
			mDMEGG.penColor_(mScopePenColor);
			sd.busThreshold.set(this.thresholdBusValue(mNumberBoxThreshold.value));  	// initialize it on the server
			bThresholdChanged = false;
			mCheckValidateEGG.enabled_(false);	// EGG validation can't be changed while running

		});

		if (gd.started, {
			var checkColor;
			if (mDMEGG.notNil, {
				mDMEGG.data = sd.movingEGGData;
				mDMEGG.normalized_(mbNormalize)
			});
			// if (ss.noiseThreshold != mNumberBoxThreshold.value, {	// If the threshold was changed,
			if (bThresholdChanged, {	// If the threshold was changed,
				sd.busThreshold.set(this.thresholdBusValue(mNumberBoxThreshold.value));  	// send it to the server
				ss.noiseThreshold = mNumberBoxThreshold.value;
				bThresholdChanged = false;
			});

			// Draw the moving EGG only if the audio clarity is above threshold
			if ((data.vrp.currentClarity ? 0) < s.vrp.clarityThreshold,
				{
					strokeCount = max(0, strokeCount - 1);
				}, {
					strokeCount = mNumberBoxCount.value;
				}
			);

			checkColor = if ((data.vrp.currentEGGvalid ? 0) == 0, { Color.gray },
				{
					if (mCheckValidateEGG.value, { Color.green }, { Color.green(0.5) })
				}
			);
			mCheckValidateEGG.palette = mCheckValidateEGG.palette.base_(checkColor);
		});

		if (gd.stopping, {
			mDMEGG = nil;
			mNumberBoxThreshold.enabled_(true);
			mCheckValidateEGG.palette = mCheckValidateEGG.palette.base_(Color.white);
			mCheckValidateEGG.enabled_(true);
		});

		// Noise thresholding
		// must not be changed interactively during fixed analysis
		bEnabled = gd.started.not or: (s.io.enabledWriteLog.not and: s.vrp.wantsContextSave.not);
		mNumberBoxThreshold.enabled_(bEnabled);
		mNumberBoxThreshold.background_( mNumberBoxThreshold.enabled.if (Color.white, Color.gray));

		[
			mButtonNormalize,
			mNumberBoxSamples,
			mNumberBoxCount
		]
		do: { | x | x.enabled_(gd.started.not); };

		this.showDiagnostics(dsg.enabledDiagnostics);

		if (dsg.guiChanged, {
			mView.background_(dsg.getThemeColor(\backPanel));
			mUV.background_(dsg.getThemeColor(\backMap));
			mScopePenColor = (dsg.getThemeColor(\curveScope));
			mView.allChildren do: ({ arg c;
				if (c.isKindOf(StaticText), { c.stringColor_(dsg.getThemeColor(\panelText)) });
				// class CheckBox does not implement .stringColor (!!)
				if (c.isKindOf(CheckBox), {
					c.palette = c.palette.windowText_(dsg.getThemeColor(\panelText));
					c.palette = c.palette.window_(dsg.getThemeColor(\backPanel));
				});
			});
			if (haveFloated > 0, {
				mUV2.background_(dsg.getThemeColor(\backMap));
			});
		});

		mUV.refresh;

		// Set the clone background even if it was created after starting
		if (haveFloated == 2, { mUV2.background_(dsg.getThemeColor(\backMap)); haveFloated = 1 });

		// If there exists a floating clone, redraw that, too
		if (haveFloated > 0, { mUV2.refresh; });
	}

	showDiagnostics { | bShow |
		[
			mStaticTextCount,
			mNumberBoxCount,
			mStaticTextSamples,
			mNumberBoxSamples
		] do: { | b, i | b.visible_(bShow) };
	}

	close {
		if (haveFloated > 0, { this.cloneFloat } );
	}
}