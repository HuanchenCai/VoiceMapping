// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //


ScopeViewer {
	var mUV, mUVholder, mUVgrid;
	var mHSpec;
	var mVSpec;
	var mfMakeGrid;

	var mGrid;
	var mGridFont;
	var mGridFontColor;
	var mPoints;
	var mAmplitudesArray;
	var mColors;
	var <>colors;
	var mPoints;

	// Timestamp bases for the client and server
	var mServerBase;
	var mClientBase;
	var mShift;

	*new { | parent, hspec, vspec |
		^super.new.init(parent, hspec, vspec);
	}

	init { | parent, hspec, vspec |
		mUVholder = UserView.new(parent, Rect());

		mUV = UserView.new(mUVholder, mUVholder.bounds.moveTo(0, 0));
		mUV.acceptsMouse_(false);

		mUVgrid = UserView.new(mUVholder, mUVholder.bounds.moveTo(0, 0));
		mUVgrid.acceptsMouse_(true);

		mHSpec = hspec;
		mVSpec = vspec;

		mGridFont = VRPViewMain.gridFont;
		mGridFontColor = Color.white;
		colors = nil;
		mShift = 0.0;

		mfMakeGrid = { arg color = mGridFontColor;
			mGrid = DrawGrid.new(
				mUV.bounds.moveTo(0, 0),
				GridLines(mHSpec),
				GridLines(mVSpec)
			)
			.gridColors_( [Color.gray(0.3), Color.gray(0.3)] )
			.smoothing_(false)
			.font_(mGridFont)
			.fontColor_(color)
			;
			mGrid.tickSpacing_(50, nil);
			mGrid.numTicks_(nil, 20);
		};

		this.reset;

		mfMakeGrid.(mGridFontColor);

		mUVholder.layout = StackLayout(
			mUV,
			mUVgrid
		).mode_(\stackAll); // Draw mUV on top of mUVgrid

		mUVgrid.drawFunc_{
			var b = mUV.bounds.insetAll(0,0,1,0);
			mGrid.bounds_(b.moveTo(0, 0));
			if (Main.versionAtLeast(3,13),
				{
					mGrid.x
					.labelAnchor_(\topLeft)
					.labelAlign_(\left)
					.labelOffset_(0@b.height.neg+2)
					.labelsShowUnits_(true)
					;
					mGrid.y
					.labelAnchor_(\topLeft)
					.labelAlign_(\left)
					.labelOffset_(3@1)
					.labelsShowUnits_(true)
					.constrainLabelExtents_(false)
					;
				}, 	{
					mGrid.x.labelOffset_(4 @ b.height.neg); // top-align the x labels
				}
			);
			mGrid.draw;
		};
		mUVgrid
		.background_(Color.black);

		mUV.drawFunc_ {
			var b = mUV.bounds;

			if (mPoints.notNil, {
				if (mPoints.notEmpty, {

					// The shift is generated due to not necessarily grabbing data at a constant and fast enough rate
					// Hence we check how long ago since we got our first timestamp both on the server and client, this
					// difference is the necessary shift. It is essentially an estimate of where the server's timestamp should be.
					var shift = mShift;
					if ( mServerBase != inf, {
						shift = (mPoints.last.x - mServerBase) - (Process.elapsedTime - mClientBase);
						mShift = shift;
					});
					Pen.use {
						var xscale = b.width / mHSpec.range;
						var yscale = b.height / mVSpec.range;
						Pen.width = 0.01;
						// Pen.smoothing_(false);
						// The UserView's coordinate system doesn't start in the middle
						Pen.translate(0, b.height / 2);
						Pen.scale(xscale, yscale.neg); // Scale the points to match the window
						Pen.translate(
							// Timestamps don't start at 0 - so move them to end at mHSpec.clipHi
							mPoints.first.x.neg + mHSpec.range - (mPoints.last.x - mPoints.first.x) + shift,
							// The vertical axis is not necessarily centered around 0 - so move the center down to 0
							( mVSpec.clipLo + mVSpec.range.half ).neg
						);

						mAmplitudesArray do: { | amps, idx |
							var t_prev = 0.0;
							var t_diff = 0.0;
							amps do: { | amp, i | mPoints[i].y = amp; };

							Pen.moveTo( mPoints.first );
							mPoints do: { | p |
								t_diff = p.x - t_prev;
								if (t_diff < 0.02,
									{
										Pen.moveTo(t_prev@(p.y));
										Pen.lineTo(p);
									},{
										Pen.moveTo(p)
									}
								);
								t_prev = p.x;
							};
							Pen.strokeColor = mColors[idx];
							Pen.stroke;
						};
					}; // Pen.use
				}); // Not empty
			}); // Not nil
		}; // drawFunc_
	} /* .init */

	//
	// Will superimpose all scoped buses if amplitudesArray contains amplitudes from more than one bus.
	//
	update { | timestamps, amplitudesArray, paused=false |
		if ( timestamps.last < mServerBase, {
			mClientBase = Process.elapsedTime;
			mServerBase = timestamps.last;
		});

		if (paused, {
			mServerBase = inf;
		});

		mPoints = timestamps collect: { | time | Point(time) };
		mAmplitudesArray = amplitudesArray;
		if (colors.isNil, {
			colors = Array.iota(mAmplitudesArray.size) collect: { | val |
				var hue = val.linlin(0, mAmplitudesArray.size, 0, 1);
				Color.hsv( hue, 0.5, 1 )
			};
		});
		mColors = colors;
		mUV.refresh;
	}

	reset {
		mServerBase = inf;
		mPoints = nil;
		mShift = 0;
	}

	stop {
		mServerBase = inf;
	}

	gridFontColor_ { arg cGrid, cFont;
		mGridFontColor = cFont;
		mGrid.gridColors_( [cGrid, cGrid] );
		mGrid.fontColor_(cFont);
		mUVgrid.refresh;
    }

	gridFontColor {
		^mGridFontColor
	}

	hspec { ^mHSpec; }
	hspec_ { | spec |
		mHSpec = spec;
		mfMakeGrid.(mGridFontColor);
	}

	vspec { ^mVSpec; }
	vspec_ { | spec |
		mVSpec = spec;
		mfMakeGrid.(mGridFontColor);
	}

	view { ^mUVholder; }

	// This lets the parent view of mUVholder (here: VRPViewSampEn.mView)
	// take control of the mouse and keyboard actions
	viewGrid { ^mUVgrid; }

	background_ { arg color;
		mUVgrid.background_(color);
	}

	refresh { { mUVholder.refresh }.defer }
}
