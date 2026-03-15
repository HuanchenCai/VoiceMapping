// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

VRPViewClusterPhon {
	// Views
	var mView;
	var mViewClusterCentroids;
	var mViewClusterStats;
	var mViewClusteringControls;

	// Controls
	var mButtonInit;
	var mButtonLearn;
	var mButtonReset;
	var mButtonLoad;
	var mButtonSave;
	var mStaticTextClusters;
	var mNumberBoxClusters;
	var mStaticTextMetrics;
	var mStaticTextCluster;
	var mSliderCluster;
	var allClusterControls;

	// Other GUI items
	var mPaletteFactory;
	var mPalette;
	var mFont;
	var mStatsHeight;

	// States
	var mSelected;	// =0 means all clusters; > 0 means cluster number
	var ccOldSelected;
	var mStarted; 	// We need to know when the server is started, just started/stopped, and by keeping a member we can do that.
	var mResetNow;	// We need to know when the server should reset the counts/centroids.
	var mCountDownFrames;  // The number of GUI updates to wait in this run before Auto Reset
	var mFramesWaited;
	var mCurrentCluster;
	var mNumberClustersLast;
	var mcDelim;
	var bRequestSaveSettings;
	var bSortRequested;
	var mbRealloc;
	var bCCreq;

	// Data
	var mLoadedClusterPhonSettings;
	var mClusterCounts;		// points per cluster
	var mClassifiedCounts;  // ditto when not learning
	var mClusterCentroids;  // the array of centroids
	var mClusterLabels; 	// array of per-cluster descriptions
	var mThisClusterLabel;  // TextField view of current label
	var mNewMapCentroid, mNewMapCentroidNumber;
	var currentLabelText;
	var bLabelChanged;

	// Settings that are not (yet) held by a control widget
	var mClusterMetrics;				// array of Metric identifier symbols
	var mMetricLows, mMetricHighs;		// arrays of ranges specified by the Metrics
	var mClusterSettingsPathName;
	var mLastPath;		// path where _phonclusters.csv was last saved or loaded

	// Constants
	var <metricID;
	classvar iRelearn = 0;
	classvar iPrelearned = 1;

	classvar iLearn = 0;
	classvar iDontLearn = 1;

	classvar iReset = 0;
	classvar iAutoReset = 1;

	classvar iLoad = 0;
	classvar iUnload = 1;

	classvar msvTitle = "Centroid coordinates";

	// GUI settings
	classvar nDefaultStatsHeight = 125;

	/////// Multi-line context-help texts  ///////////////////

	var helpInitButton =
"Chooses which phonation-type clusters to start with.
Relearn: discard the current clusters and start learning new ones.
Pre-learned: keep using the clusters learned so far,
or that have been loaded from a _cPhon.csv file.";

	var helpLearnButton =
"Turns learning of phonation-type clusters On or Off.
On:  clustering -- \"train\" the clusters using the incoming signals.
Off: classification -- use the current clusters
     to classify the signals (Init must be Pre-learned).";

	var helpResetButton =
"For resetting the current phonation-type clusters (Learning must be On).
When FonaDyn is analyzing, pushing Reset Counts clears the clusters immediately and starts over.
When FonaDyn is idle, it arms for an auto reset once 0.2s of phonation have been detected. (F5)";

	var helpLoadButton =
"Load Clusters lets you select and load an existing *_cPhon.csv file;
or, you can drag-and-drop a *_cPhon.csv file onto this button.
Unload clears the current clusters and allows a new set to be loaded.";

	var helpSaveButton =
"Lets you save the current phonation-type clusters to a text file
that you name. If you do not give a .csv extension, then \"_cPhon.csv\"
will be added by default (recommended).
* = not saved";

	var helpNclusters =
"Before starting, choose a number of phonation type clusters here (1-10).
More than 6 is rarely useful.";

	var helpNmetrics =
"To configure the number of metrics to cluster,
and their ranges 0%-100%,
edit a _cPhon.csv file and load it.
(Handbook 3.5.6)";

	var helpSlider =
"Select one clustered phonation type for display, or far left for All.
This selection will propagate to the map display as well.";

	var helpCentroids =
"This graph displays the cluster centroids of the clustered phonation types.
Each metric has a range from 0% (center) to 100% (periphery).
The smaller circle is at 50% for that metric.

To load new clusters, or a new clustering setup,
you can drag-and-drop a _cPhon.csv file here.

Left-click here to show or hide the clustering setup controls.";


	var helpStats =
"The height of the bars shows the number of phonatory cycles assigned to each cluster.
Click-left on a bar to see the centroid radar plot for that cluster.
Click-left near the top of the graph to see all the centroids.
Re-ordering: Shift-click left or right on a bar to make two clusters swap places.

To load new clusters, or a new clustering setup,
you can drag-and-drop a _cPhon.csv file here.";

	var helpControls =
"First select a cluster using the large slider above this panel.
The centroid coordinates (=metric averages) for that cluster will appear.
The min and max for each metric are shown as 0% and 100%.
These are defined in the loaded _cPhon.csv file.

The little squares move when FonaDyn is learning new phonation types.
You can give a label to each phonation type in the edit box at the bottom.

If FonaDyn is stopped and Learning is On,
you can specify custom centroids by dragging the squares.
Or, reposition the squares using the arrow keys.

If Listen: map is active, you can pick centroids straight from the voice map;
left-click on it, then press the number key of the cluster.

To go back to the bar graph, left-click on the radar plot.";

	/////////////////////////////////////

	*new { | view |
		^super.new.init(view);
	}

	setPalette { | whichCluster, howManyClusters |
		mPaletteFactory.setClusters(whichCluster, howManyClusters);
		mPalette = mPaletteFactory.palette.deepCopy;
	}

	init { | view |
		var gridFont = VRPViewMain.gridFont;
		var gridGreen = Color.new(0.0, 0.6, 0.4);
		mView = view;
		mView.setProperty(\contextHelp, "This panel displays and controls the clustering of phonation types.");

		metricID = VRPSettings.iClustersPhon;		// for passing with change notifications
		mLastPath = thisProcess.platform.recordingsDir;  // Should be from MainViewGeneral instead
		bRequestSaveSettings = false;
		bSortRequested = false;
		bCCreq = false;
		mNumberClustersLast = 5;
		bLabelChanged = false;
		mbRealloc = false;
		mNewMapCentroid = nil;

		this addDependant: VRPViewMaps.mAdapterUpdate;

		mPaletteFactory = VRPSettings.metrics[VRPSettings.iClustersPhon].deepCopy;

		// View that shows the radar plot of the centroids
		mViewClusterCentroids = UserView(mView, mView.bounds);
		mViewClusterCentroids
		.background_(Color.black)
		.drawFunc_{ | uv |
			this.drawCentroids(mViewClusterCentroids);
		};
		mViewClusterCentroids.setProperty(\contextHelp, helpCentroids);

		// Allow dropping of _cPhon.csv files onto the radar plot
		mViewClusterCentroids.canReceiveDragHandler_({|v, x, y|
			var str, bOK = false;
			str = v.class.currentDrag;
			if ((mButtonLoad.value == iLoad) and: (str.class == String), {
				if (VRPDataClusterPhon.testSuffix(str), {
					bOK = true;
				})
			} );
			bOK
		})
		.receiveDragHandler_({|v, x, y|
			var str, bOK = false;
			str = v.class.currentDrag;
			this.loadClusterSettingsPath(str);
			mButtonLoad.value = iUnload;
		});


		// View that shows the bar graph of the cluster point counts
		mViewClusterStats = UserView(mView, mView.bounds);
		mViewClusterStats
		.background_(Color.black)
		.acceptsMouse_(true)
		.drawFunc_{ | uv |
			this.drawStats(mViewClusterStats);
		};
		mViewClusterStats.canReceiveDragHandler = mViewClusterCentroids.canReceiveDragHandler;
		mViewClusterStats.receiveDragHandler = mViewClusterCentroids.receiveDragHandler;
		mViewClusterStats.setProperty(\contextHelp, helpStats);


		// View that holds the metric scaling control panel
		mViewClusteringControls = CompositeView(mView, mView.bounds);
		mViewClusteringControls
		.background_(Color.gray)
		.visible_(false);
		mViewClusteringControls.canReceiveDragHandler = mViewClusterCentroids.canReceiveDragHandler;
		mViewClusteringControls.receiveDragHandler = mViewClusterCentroids.receiveDragHandler;
		mViewClusteringControls.setProperty(\contextHelp, helpControls);

		mLoadedClusterPhonSettings = nil;
		mClusterCounts = nil;
		mClusterCentroids = nil;
		mClassifiedCounts = nil;
		mClusterLabels = nil;
		mCurrentCluster = 0; // avoid nil, to prevent certain palette errors

		mFont = VRPViewMain.staticFont;
		mStatsHeight = nDefaultStatsHeight;
		mStarted = false;
		mResetNow = false;
		mCountDownFrames = -1;
		mcDelim = VRPMain.cListSeparator ;	// column separator in CSV files - locale-dependent

		this.initMenu();
		this.setPalette (0, mNumberBoxClusters.value);

		// Click on a colored column to select that cluster
		// Click in the upper third of the window to display all clusters
		// Hold down Ctrl and click left or right on a column to shift the cluster order
		mViewClusterStats.mouseDownAction_{
			| uv, x, y, mod, buttonNumber |
			var retVal = nil;
			if (mClusterCounts.notNil, {
				var idx;
				idx = ((x / uv.bounds.width) * mClusterCounts.size).asInteger;
				case
				// Ctrl-click on bars to swap two clusters.
				// On the Mac, a bug turns ctrl-left-mouse-down into ctrl-right-mouse-down
				// - use the shift key instead
				{ mStarted.not and: { (mod.isCtrl) or: (mod.isShift) } }
				{
					switch (buttonNumber,
						0, { this.shiftorder(idx, -1) },
						1, { this.shiftorder(idx,  1) }
					);
					retVal = true;
				}
				{ buttonNumber == 0 }
				{
					if ((y < (uv.bounds.height/3)),
						{
							idx = 0;
							mSliderCluster.valueAction_(idx);
						},
						{
							mSliderCluster.valueAction_((idx+1)/mClusterCounts.size);
						}
					);
					retVal = true;
				};
			});
			retVal
		};

		mViewClusterCentroids.mouseDownAction_{
			| uv, x, y, mod, buttonNumber |
			mViewClusteringControls.visible_(mViewClusteringControls.visible.not);
			mViewClusterStats.visible_(mViewClusterStats.visible.not);
		};

		mView.layout_(
			VLayout(
				[
					HLayout(
						[mButtonInit, stretch: 1],
						[mButtonLearn, stretch: 1],
						[mButtonReset, stretch: 1],
						[mButtonLoad, stretch: 1],
						[mButtonSave, stretch: 1]
					), stretch: 1
				],

				[
					HLayout(
						[mStaticTextClusters, stretch: 1],
						[mNumberBoxClusters, stretch: 1],
						[mStaticTextMetrics, stretch: 1],
						[mStaticTextCluster, stretch: 1],
						[mSliderCluster, stretch: 3]
					), stretch: 1
				],

				[
					HLayout(
						[mViewClusterCentroids, stretch: 1],
						[mViewClusteringControls, stretch: 1],
						[mViewClusterStats, stretch: 1]
					), stretch: 2
				] // Force the menu to take up as little space as possible!
			)
		);
		mView.layout.margins_(5);
	} /* .init */

	initMenu {
		var static_font = VRPViewMain.staticFont;
		var button_font = VRPViewMain.qtFont;

		////////////////////////////////////////////////////////////////////

		mButtonInit = Button(mView, Rect())
		.font_(button_font)
		.enabled_(false)
		.states_([
			["Init: Relearn"],
			["Init: Pre-learned"]
		])
		.action_({ | btn |
			this.updateMenu;
		})
		.canReceiveDragHandler_({ |v| v.class.prClearCurrentDrag; });
		mButtonInit.setProperty(\contextHelp, helpInitButton);

		/////////////////////////////////////////////////////////////////////
		/////////////////////////////////////////////////////////////////////

		mButtonLearn = Button(mView, Rect())
		.font_(button_font)
		.enabled_(false)
		.states_([
			["Learning: On"],
			["Learning: Off"]
		])
		.action_({ | btn |
			this.updateMenu;
		})
		.canReceiveDragHandler_({ |v| v.class.prClearCurrentDrag; });
		mButtonLearn.setProperty(\contextHelp, helpLearnButton);

		/////////////////////////////////////////////////////////////////////
		/////////////////////////////////////////////////////////////////////

		mButtonReset = Button(mView, Rect())
		.font_(button_font)
		.states_([ 	["Reset Counts"], ["Auto Reset", Color.black, Color.hsv(0.12, 1, 1)] ])
		.mouseDownAction_( { arg btn;
			var ret_val = nil;
			if ( mStarted, {
				// The server is started - so let it deal with the reset
				mResetNow = true;
				ret_val = true;
				btn.value_(0);
			},{
				// The server is not started - so lets deal with it locally.
				if ( mClusterCounts.notNil, {
					mClusterCounts.fill(0);
					mClassifiedCounts = mClusterCounts;
				});
			});
			mStatsHeight = nDefaultStatsHeight;
			mViewClusterStats.refresh;
			ret_val
		} )
		.canReceiveDragHandler_({ |v| v.class.prClearCurrentDrag; });
		mButtonReset.setProperty(\contextHelp, helpResetButton);

		/////////////////////////////////////////////////////////////////////
		/////////////////////////////////////////////////////////////////////

		mButtonLoad = Button(mView, Rect())
		.font_(button_font)
		.states_([
			["Load Clusters"],
			["Unload"]
		])
		.action_({ | btn |
			var load = btn.value == iUnload;
			if ( load,
				{
					this.loadClusterSettingsDialog;
				}, {
					mClusterCounts = nil;
					mClassifiedCounts = nil;
					mClusterCentroids = nil;
					mCurrentCluster = 0; // avoid nil, to prevent certain palette errors
				}
			);
			this.updateMenu;
		})
		.canReceiveDragHandler_({|v, x, y|
			var str, bOK = false;
			str = v.class.currentDrag;
			if ((v.value == iLoad) and: (str.class == String), {
				if (VRPDataClusterPhon.testSuffix(str), {
					bOK = true;
				} , {
					"Invalid cluster data.".warn;
				})
			} );
			bOK
		})
		.receiveDragHandler_({|v, x, y|
			var str, bOK = false;
			str = v.class.currentDrag;
			this.loadClusterSettingsPath(str);
			v.value = iUnload;
		});
		mButtonLoad.setProperty(\contextHelp, helpLoadButton);

		/////////////////////////////////////////////////////////////////////
		/////////////////////////////////////////////////////////////////////

		mButtonSave = Button(mView, Rect())
		.font_(button_font)
		.enabled_(false)
		.states_([
			["Save Clusters"]
		])
		.action_({
			bRequestSaveSettings = true;
			// Will invoke this.saveClusterSettingsDialog;
		})
		.canReceiveDragHandler_({ |v| v.class.prClearCurrentDrag; });

		// Method to postfix the button's label, or not, without changing its state
		mButtonSave.addUniqueMethod(\setPostfix, { | btn, str |
			btn.states = [[ ("Save Clusters"++str).asString]];
		});
		mButtonSave.setProperty(\contextHelp, helpSaveButton);

		/////////////////////////////////////////////////////////////////////

		mStaticTextClusters = StaticText(mView, Rect(0, 0, 100, 0))
		.string_("Phon clusters:")
		.font_(static_font);
		mStaticTextClusters
		.fixedWidth_(mStaticTextClusters.sizeHint.width)
		.fixedHeight_(20)
		.stringColor_(Color.white);
		mStaticTextClusters.setProperty(\contextHelp, helpNclusters);

		mNumberBoxClusters = NumberBox(mView, Rect(0, 0, 100, 35))
		.font_(static_font)
		.value_(5)							// This is the default value
		.clipLo_(2)
		.clipHi_(VRPSettingsClusterPhon.nMaxClusters)
		.step_(1)
		.scroll_step_(1)
		.fixedWidth_(24)
		.focusGainedAction_( { bCCreq = false } )	// kludge to get bCCreq unstuck if needed
		.action_{ |bn|
			if ((bn.value != mNumberClustersLast), {
				if (bCCreq, {
					// Avoid re-entrance while the change is being processed
					bn.value = mNumberClustersLast;
				}, {
					bCCreq = true;
					mNumberClustersLast = bn.value;
				});
			});
		};
		mNumberBoxClusters.setProperty(\contextHelp, "You can edit numbers & ENTER, use the arrow keys, or drag vertically.");

		/////////////////////////////////////////////////////////////////////
		/////////////////////////////////////////////////////////////////////

		mStaticTextMetrics = StaticText(mView, Rect(0, 0, 100, 0))
		.string_("Metrics:xxx")
		.font_(static_font);
		mStaticTextMetrics
		.fixedWidth_(mStaticTextMetrics.sizeHint.width)
		.fixedHeight_(20)
		.stringColor_(Color.white)
		.align(\right);
		mStaticTextMetrics.setProperty(\contextHelp, helpNmetrics);

		/////////////////////////////////////////////////////////////////////

		mStaticTextCluster = TextField(mView, [0, 0, 100, 20]);
		mStaticTextCluster
		.font_(static_font)
		.resize_(4)
		.align_(\right)
		.fixedWidth_(24)
		.enabled_(false);

		mSliderCluster = Slider(mView, [0, 0, mView.bounds.width, 30]);
		mSliderCluster
		.resize_(4)
		.maxHeight_(30)
		.value(0.0);
		mSliderCluster.setProperty(\contextHelp, helpSlider);

		// Ignore default keys if Alt is pressed
		mSliderCluster.keyDownAction = { |v, char, mod, unicode, keycode, key|
			var ret_val = nil;
			if (mod.isAlt, { ret_val = false },
				{ ret_val = v.defaultKeyDownAction(char, mod, unicode, keycode, key)}
			);
			ret_val
		};

		/////////////////////////////////////////////////////////////////////
		// Initialize the GUI members from global constants
		/////////////////////////////////////////////////////////////////////

		// The "mClusterMetrics" array controls which metrics will be clustered,
		// and their order, clockwise from the top.
		// For the time being, there is no GUI for specifying mClusterMetrics,
		// except to load it from a _cPhon.csv file.
		// mClusterMetrics = [\CPP, \Crest, \SpecBal, \SampEn, \Qci, \Qdelta];  // standard combo
		// mClusterMetrics = [\Clarity, \CPP, \Crest, \SpecBal];	// Audio only
		// mClusterMetrics = [\SampEn, \Qci, \Qdelta, \HRFegg];		// EGG only

		mClusterMetrics = VRPSettingsClusterPhon.defaultMetrics collect: { | id, ix |
			VRPSettings.metrics[id.asInteger].class.symbol;
		};

		mMetricLows  = [];
		mMetricHighs = [];
		mClusterMetrics do: { arg sym, ix;
			VRPSettings.metrics do: { arg m, jx;
				if (m.class.symbol == sym, {
					m.fnStandardizeMsg.value();   // initializes unspecified ranges
					mMetricLows  = mMetricLows.add(m.rangeLow);
					mMetricHighs = mMetricHighs.add(m.rangeHigh);
				});
			};
		};
		mSelected = 0;
		this.initCCpanel(mViewClusteringControls, mClusterMetrics);
		this.updateMenu;
	} /* initMenu */

	pressReset {
		if ( mStarted, {
			// The server is started - so let it deal with the reset
			mResetNow = true;
		},{
			if (mButtonReset.enabled, {
				mButtonReset.valueAction = mButtonReset.value.asBoolean.not.asInteger;
			});
		})
	}


	/////////////////////////////////////////////////////////////////////
	// Fill in the view that is the clustering control panel
	/////////////////////////////////////////////////////////////////////

	initCCpanel { arg mvcc, mcm, scPhon=nil;
		var ccGridLayout;
		var cbAllMetrics = [nil];
		var sz = Size(32, 18);
		var msv, bkColorLog, listHeadings;
		var headings = [];
		var bottomRow = [nil];

		mvcc.removeAll;
		bkColorLog = Color.hsv(0.67, 0.2, 0.8);
		msv = MultiSliderView.new(mvcc);
		msv
		.size_(mcm.size)
		.indexIsHorizontal_(false)
		.editable_(true)
		.elasticMode_(1)
		.colors_(Color.black, Color.gray(0.8));


		// A MultiSliderView does not respect indexIsHorizontal for key mapping,
		// so teach it.
		msv.keyDownAction_{ arg view, char, mod, uni, keycode, key;
			view.step_(if(mod.isCtrl, 0.05, 0.01));
			key.switch (
			QKey.up, { view.index = view.index - 1 },
			QKey.down, { view.index = view.index + 1 },
			QKey.right, { view.currentvalue = view.currentvalue + view.step },
			QKey.left, { view.currentvalue = view.currentvalue - view.step }
		)};

		if (mSelected > 0, {
			msv.value_(mClusterCentroids[mSelected-1])
		});

		// Build a title row
		listHeadings = List.newFrom([ "Metric", \right, "0%", \center, msvTitle, \center, "100%", \center, "unit", \left]);
		listHeadings.pairsDo({ | str, al |
			headings = headings.add(StaticText(mvcc).string_(str).align_(al).stringColor_(Color.gray))
		});
		cbAllMetrics[0] = headings;

		mClusterMetrics do: ({ arg sym, ixm;
			var cbRow = [];
			VRPSettings.metrics do: { arg m;
				var ctrl, rLow, rHigh;
				if (m.class.symbol == sym, {
					var stdMsg = m.fnStandardizeMsg;   // initializes unspecified ranges
					cbRow = cbRow.add(ctrl = StaticText.new(mvcc).string_(m.class.symbol.asString).stringColor_(Color.gray(0.8)));
					ctrl.align_(\right);
					rLow = if (scPhon.isNil, { mMetricLows[ixm] }, { scPhon.rangeLows[ixm] ? (mMetricLows[ixm]) });
					cbRow = cbRow.add(ctrl = NumberBox.new(mvcc).value_(rLow));
					ctrl
					.align_(\center)
					.fixedSize_(sz)
					.enabled_(false); // Can be changed to true once saving has been implemented
					if (stdMsg[0] == 'explin', { ctrl.background_(bkColorLog) });

					// Insert the multislider view in row 0
					if (ixm == 0, {
						cbRow = cbRow.add([msv, rows: mClusterMetrics.size, stretch: 1])
					}, {
						cbRow = cbRow.add(nil);
					});

					rHigh = if (scPhon.isNil, { mMetricHighs[ixm] }, { scPhon.rangeHighs[ixm] ? (mMetricHighs[ixm]) });
					cbRow = cbRow.add(ctrl = NumberBox.new(mvcc).value_(rHigh));
					ctrl
					.align_(\center)
					.fixedSize_(sz)
					.enabled_(false); // Will be changed to true once saving has been implemented
					if (stdMsg[0] == 'explin', { ctrl.background_(bkColorLog) });

					cbRow = cbRow.add(ctrl = StaticText.new(mvcc).string_(m.unit).stringColor_(Color.gray(0.8)));
					ctrl.align_(\left);
				});
			};
			if (cbRow.notEmpty, { cbAllMetrics = cbAllMetrics.add( cbRow ) });
		});

		mThisClusterLabel = TextField.new(mvcc);
		mThisClusterLabel
		.align_(\center)
		.resize_(2)
		.minWidth_(120)
		.string_("<label not set>")
		.action_({ arg tf;
			// User is editing the label text:
			// signal whether mClusterLabels needs changing
			bLabelChanged = (tf.string != currentLabelText);
			tf.background_(Color.gray);
		});

		// Build the bottom row
		bottomRow[0] = [ StaticText.new(mvcc).string_("Edit label...").stringColor_(Color.gray(0.8)),
			a: \right, columns: 2];
		bottomRow = bottomRow.add([mThisClusterLabel, s: 2, a: \center]);
		bottomRow = bottomRow.add( [ StaticText.new(mvcc).string_("...& Enter").stringColor_(Color.gray(0.8)),
			a: \left, columns: 2]);
		bottomRow = bottomRow.add(nil);
		cbAllMetrics = cbAllMetrics.add(bottomRow);

		// For stretchable height at the bottom
		cbAllMetrics = cbAllMetrics.add(nil ! 5);

		// Save in an instance variable of "this"
		allClusterControls = cbAllMetrics.deepCopy;
		msv.focusLostAction_({ allClusterControls[0][2].string_(msvTitle) });

		// Now we can create and adopt the layout
		ccGridLayout = GridLayout.rows(
			*allClusterControls[(0..(allClusterControls.size-1))] 	// weird syntax, but it works
		);
		ccGridLayout.setRowStretch(0, 0);
		ccGridLayout.setRowStretch(allClusterControls.size-1, 5);
		ccGridLayout.vSpacing_(4);
		mvcc.layout = ccGridLayout;
	} /* .initCCpanel */

	setCCsliders { arg selCluster;
		var color, colorLabelText, msv, valueArray, bottomRowNo, stCurrentPercent;

		msv = allClusterControls[1][2][0];
		stCurrentPercent = allClusterControls[0][2];
		if (selCluster <= 0 or: mClusterCentroids.isNil,
			{
				valueArray = (0.0 ! msv.size);
				color = msv.parent.background;
				mThisClusterLabel.string_("Edit label & Enter");
				stCurrentPercent.string_(msvTitle);
				mThisClusterLabel.enabled_(false);
			}, {
				valueArray = mClusterCentroids[selCluster-1];
				color = mPalette.(selCluster-1);
				mThisClusterLabel.enabled_(true);
				if (mClusterLabels.notNil, {
					// If the user has changed the string, modify the mClusterLabel
					if (bLabelChanged, {
						mClusterLabels[selCluster-1] = currentLabelText = mThisClusterLabel.string;
					}, {
						if (mThisClusterLabel.hasFocus.not, {
							mThisClusterLabel.string_(mClusterLabels[selCluster-1])
						});
					});
				});
			}
		);
		msv.background_(color);
		msv.step_(0.0);

		colorLabelText = Color.gray((1.0 - (color.asArray[0..2].sum/3)).round);
		bottomRowNo = allClusterControls.size-2;
		mThisClusterLabel = allClusterControls[bottomRowNo][1][0];
		mThisClusterLabel.stringColor_(colorLabelText).background_(color);

		if (mStarted, {
			msv.value_(valueArray); // Animate sliders while running
		}, {
			// Not running
			if ((mNewMapCentroidNumber.notNil
				and: { mNewMapCentroid.notNil }		// User has picked a centroid location from the map
				and: { mNewMapCentroidNumber.inclusivelyBetween(1, mNumberBoxClusters.value) }
				and: { mButtonLearn.value == iLearn }), {
					var newValueArray = [];
					var c = mNewMapCentroidNumber-1;
					mClusterMetrics do: ({ arg sym, ixm;
						VRPSettings.metrics do: { arg m;
							if (m.class.symbol == sym, {
								var val, normVal;
								var msg = m.msgStandardize;
								val = mNewMapCentroid[ixm];
			// msg is taken directly from the metrics;
			// but lowRange and highRange should be taken from the local arrays instead
								msg[1] = mMetricLows[ixm];
								msg[2] = mMetricHighs[ixm];
								normVal = val.performMsg(msg);
								newValueArray = newValueArray.add(normVal);
							})
						};
					});
					mClusterCentroids[c] = newValueArray;
					mClusterCounts[c] = 10;
					mButtonLoad.value_(iUnload);
					mButtonSave.setPostfix("*");
					format("Phonation type cluster % set to %", mNewMapCentroidNumber, mNewMapCentroid).postln;
			});

			// "Modify centroid" request has now been serviced
			mNewMapCentroid = nil;

			if (msv.hasFocus and: (selCluster > 0) and: (mButtonLearn.value == iLearn),
				{
					msv.showIndex_(true);
					mClusterCentroids[selCluster-1] = msv.value;  // Learn from user interaction
					stCurrentPercent.string_((msv.currentvalue*100).round(0.1)+"%");
					mButtonLoad.value_(iUnload);
					mButtonSave.setPostfix("*");	// GUI shows a change
				}, {
					var tStr;
					msv.showIndex_(false);
					msv.value_(valueArray); // Update sliders with any changes
					tStr = if (selCluster == 0, msvTitle, { "Average:"+(msv.value.mean*100).round(0.1)++"%" });
					stCurrentPercent.string_(tStr);
			});
		});

	} /* setCCsliders */

	updateMenu {
		if ( mStarted.not, { // All disabled while it is started

			// Update the slider
			var req_step = 1 / (mNumberBoxClusters.value);

			if ( mSliderCluster.step != req_step, {
				mSliderCluster
				.step_(req_step)
				.action_{
					mSelected = (mSliderCluster.value*mNumberBoxClusters.value).round(1).asInteger;

					// Update the cluster text
					mStaticTextCluster.string_(
						// "Cluster: " ++
						if ( mSelected == 0, "All", mSelected.asString )
					);

					// Signal a change of the selected cluster,
					// so that the map display can change, too
					this.changed(this, \selectCluster, mSelected);
				};

				// Reset the slider to 0 since it is no longer valid
				mSliderCluster.valueAction_(0);
				mSelected = 0;
			});

			// Enable/Disable controls depending on the current states
			mButtonLoad.enabled_(true); // Load is always available

			switch (mButtonLoad.value,
				iLoad, {
					mButtonInit
					.enabled_(false)
					.value_(iRelearn); // Must relearn without any prelearned data

					// User can change the # of clusters when nothing is loaded
					mNumberBoxClusters
					.enabled_(true);
				},

				iUnload, {
					mButtonInit
					.enabled_(true); // May choose to use prelearned data or not

					// Cannot update the # of clusters since we have data loaded
					mNumberBoxClusters
					.enabled_(false);
				}
			);

			switch (mButtonInit.value,
				iRelearn, {
					mButtonLearn
					.enabled_(false)
					.value_(iLearn); // Must learn with relearn active
				},

				iPrelearned, {
					mButtonLearn
					.enabled_(true); // May choose to continue learning or not

					// Cannot update the # of clusters with prelearned data
					mNumberBoxClusters
					.enabled_(false);
				}
			);

			// Can only use reset while learning is on
			mButtonReset
			.enabled_( mButtonLearn.value == iLearn );

			// Cannot save without any data
			mButtonSave
			.enabled_( mButtonLoad.value == iUnload );

			// If learning is on, the _cPhon.csv file is no longer valid
			if (mButtonLearn.value == iLearn, {
				mClusterSettingsPathName = nil;
			});
		});
		mStaticTextMetrics.string_(format("Metrics: %", mClusterMetrics.size));

		if (mViewClusteringControls.visible or: mNewMapCentroid.notNil, {
			this.setCCsliders(mSelected);
		});

	} /* updateMenu */

	saveClusterSettingsDialog { arg cSettings;
		var bUnsaved = mButtonSave.string.endsWith("*");
		VRPMain.savePanelPauseGUI(
			okFunc:
			{ | path |
				mLastPath = PathName.new(path).pathOnly;
				cSettings.saveClusterPhonSettings(path);
				mClusterSettingsPathName = path;
				mButtonSave.setPostfix("");
			},
			cancelFunc:
			{
				mButtonSave.setPostfix( if(bUnsaved, "*", "") );
			},
			path: mLastPath,
			wantedSuffix: VRPDataClusterPhon.csvSuffix[\PhoncsvSuffix]);
	}

	loadClusterSettingsPath{ arg inPath=nil;
		var c, mCount, chosenPath;
		var tempClusterSettings = VRPSettingsClusterPhon.new(nil);

		if (inPath.notNil, {
			chosenPath = inPath;

			#c, mCount = tempClusterSettings.loadClusterPhonSettings(chosenPath);
			mClusterSettingsPathName = chosenPath;
			if (c >= 2, {
				mLoadedClusterPhonSettings = tempClusterSettings;   // Queue for .stash
				mLoadedClusterPhonSettings.learn = false;
				mLastPath = PathName.new(chosenPath).pathOnly;
				mButtonSave.setPostfix(""); //No changes yet
			}, {
				format("Could not parse the file %", PathName.new(chosenPath).fileName).error
			});
		});
	} /* loadClusterSettingsPath{} */

	loadClusterSettingsDialog {
		VRPMain.openPanelPauseGUI(
			{ | path |
				this.loadClusterSettingsPath(path);
			} , {
				mButtonLoad.value = iLoad; // Cancelled
		} , path: mLastPath);
	}

	reorder { arg newOrder;
		var tmp, bOK;
		bOK = true;
		if ((newOrder.class == Array) and: (newOrder.size == mClusterCounts.size),
			{
				newOrder.do { |elem, i| if (elem.class != Integer,  { bOK = false } )};
				if (bOK, {
					// tmp = mClusterCounts[newOrder];		// .deepCopy;
					// mClusterCounts = tmp;
					// tmp = mClusterCentroids[newOrder];	// .deepCopy;
					// mClusterCentroids = tmp;
					// tmp = mClusterLabels[newOrder]; 	// .deepCopy;
					// mClusterLabels = tmp;
					mClusterCounts = mClusterCounts[newOrder];
					mClusterCentroids = mClusterCentroids[newOrder];
					mClusterLabels = mClusterLabels[newOrder];
					mClusterSettingsPathName = nil; // Centroids no longer match those loaded from file
					mButtonSave.setPostfix("*");	// Show unsaved status
					this.changed(this, \reorderClusters, newOrder);
				});
		});
	}

	// Shift cluster iCluster by nSteps (< 0 left, > 0 right)
	shiftorder { arg iCluster, nSteps;
		var nC, kC;
		var newOrder;
		nC = mClusterCounts.size;
		kC = (iCluster + nSteps).mod(nC);
		newOrder = (0..nC-1).swap(iCluster, kC);
		this.reorder(newOrder);
	}

	sortClusters {
		var newOrder;
		var oldList = mClusterCentroids collect: { | c, ix | [c.sum, ix] };
		oldList.sort ( { | s1, s2 | s1[0] > s2[0] } );
		newOrder = oldList collect: { | si | si[1] }; 		    // get the new ix order
		this.reorder(newOrder);
	}

	stash { | settings, trace=0 |
		var cs = settings.clusterPhon;
		// New clusters loaded from _cPhon.csv file or Archive
		if (mLastPath.isNil, { mLastPath = settings.io.outDir } );
		mClusterCounts = cs.pointsInCluster;
		mClusterCentroids = cs.centroids;
		mClusterMetrics = cs.clusterMetrics;
		mClusterLabels = cs.clusterLabels;
		mMetricLows = cs.rangeLows;
		mMetricHighs = cs.rangeHighs;
		mClusterSettingsPathName = cs.filePath;
		if (cs.filePath.notNil, {
			mButtonLoad.value_(iUnload);
			mButtonSave.setPostfix("");
		});
		if (mNumberBoxClusters.value != cs.nClusters, {
			mNumberBoxClusters.value = cs.nClusters;
			mbRealloc = true;
		});
		mButtonInit.value_(cs.initialize.if (iPrelearned, iRelearn));
		mButtonLearn.value_(cs.learn.if (iLearn, iDontLearn));
		if (trace >= 3, {
			this.initCCpanel(mViewClusteringControls, mClusterMetrics, cs);
		});
		mButtonReset.value_(cs.autoReset.if (iAutoReset, iReset));
		mView.setProperty(\visible, cs.isVisible, true);
	} /* .stash */

	fetch { | settings |
		var nCpre, nCpost;
		var cs = settings.clusterPhon;
		nCpre = nCpost = cs.nClusters;

		case
		{ cs.stashRequested }
		{	// A new phon-settings has been loaded by a script
			settings.clusterPhon = cs.getSettings;
			this.stash(settings, trace: 4);
			nCpost = mClusterCentroids.size;
			mbRealloc = false;
		}

		{ mLoadedClusterPhonSettings.notNil }
		{	// A new phon-settings file has been opened by the user
			settings.clusterPhon = mLoadedClusterPhonSettings;
			this.stash(settings, trace: 3);
			nCpost = mClusterCentroids.size;
			mButtonLoad.value_(iUnload);
			mbRealloc = false;
			mLoadedClusterPhonSettings = nil;
		}

		{ bCCreq }
		{	// The user has changed the number of clusters manually
			nCpost = mNumberBoxClusters.value.asInteger;
			cs.allocCentroids(nCpost);
			this.stash(settings, trace: 2);
			mButtonLoad.value_(iLoad);
		}

		{ settings.waitingForStash() }
		{	// A new setting has been set from a script,
			// or all settings have been retrieved from the archive.
			this.stash(settings, trace: 1);
			// nCpre = -1 ; // dummy value to force a palette change below
		}

		// If nothing has yet been loaded or learned, get the default settings
		// so that they can be edited manually
		{ mClusterCentroids.isNil } {
			settings.clusterPhon.allocCentroids(nCpost = mNumberBoxClusters.value);
			this.stash(settings, trace: 0);
			mbRealloc = false;
			mButtonLoad.value_(iLoad);
		};  /* case */

		if ((bSortRequested and: mStarted.not)
			and: (mButtonLearn.value == iLearn)
			and: (mButtonInit.value == iRelearn), {
				"Sorting phonation type clusters...".postln;
				this.sortClusters;
				bSortRequested = false;
				VRPData.breatheCycles(-1);
				mButtonInit.value_(iPrelearned);
			}
		);

		cs.clusterLabels = mClusterLabels;
		cs.pointsInCluster = mClusterCounts;
		cs.centroids = mClusterCentroids;

		cs.clusterMetrics = mClusterMetrics;
		cs.rangeLows = mMetricLows;
		cs.rangeHighs = mMetricHighs;

		{ cs.isVisible = mView.visible }.defer;

		mNewMapCentroid = cs.mapCentroid.deepCopy;
		mNewMapCentroidNumber = cs.mapCentroidNumber;
		cs.mapCentroid = nil;

		cs.filePath = mClusterSettingsPathName;
		cs.initialize = (mButtonInit.value == iPrelearned);
		cs.learn = (mButtonLearn.value == iLearn);
		cs.autoReset = (mButtonReset.value == iAutoReset);

		if ((nCpre != nCpost), {
			this.setPalette(0, nCpost);
			this.changed(this, \numberOfClusters, nCpost);
			bCCreq = false;
		});


		// Arrange so that the map(s), too, will show the new label
		if (bLabelChanged, {
			settings.waitingForStash = true;
			bLabelChanged = false;
		});

		if (bRequestSaveSettings, {
			this.saveClusterSettingsDialog(cs);
			bRequestSaveSettings = false;
		})
	}  /* .fetch */

	updateData { | data |
		var cd = data.clusterPhon;
		var cs = data.settings.clusterPhon;
		var csg = data.settings.general;

		if (csg.guiChanged, {
			mView.background_(csg.getThemeColor(\backPanel));
			[
				mViewClusterCentroids,
				mViewClusterStats,
				mViewClusteringControls
			] do: { | c | c.background_(csg.getThemeColor(\backGraph)) };
			mView.allChildren.do ({ arg c;
				if (c.isKindOf(StaticText), { c.stringColor_(csg.getThemeColor(\panelText)) });
				// class CheckBox does not implement .stringColor (!!)
				if (c.isKindOf(CheckBox), {
					c.palette = c.palette.windowText_(csg.getThemeColor(\panelText));
					c.palette = c.palette.window_(csg.getThemeColor(\backPanel));
				});
			});
		});

		// NOTE: We check if the server is started with mStarted, since we rather care
		// about not missing out on data at the end, than starting to grab data at the
		// first possible chance.
		if (mStarted, {
			var cMax = cd.centroids.size - 1;
			// Grab the newly updated data
			mClusterCounts = cd.pointsInCluster;
			mClusterCentroids = cd.centroids;

			// Guard against possible bad initial values in currentClusterPhon
			mCurrentCluster = (data.vrp.currentClusterPhon ? 0).clip(0, cMax).asInteger;

			// Wait until the clarity has been above threshold
			// for "iFramesToReset" consecutive GUI updates,
			// and then issue an Auto Reset of the clusters
			if ((mCountDownFrames > 0) and: data.vrp.currentClarity.notNil,
				{	// Increment if clarity is above threshold, otherwise start over
					if (data.vrp.currentClarity >= VRPSettings.metrics[VRPSettings.iClarity].minVal,
						{ mFramesWaited = mFramesWaited + 1 } , { mFramesWaited = 0 }
					);
					if (mFramesWaited >= mCountDownFrames,
						{
							mResetNow = true;
							mCountDownFrames = 0;
							mButtonReset.value = iReset;
						}
					);
				}
			);

			if ( mResetNow, {
				Date.localtime.format("RESET Phon clusters %H:%M:%S").postln;
				cd.resetNow = true;
			});

			// Use this mechanism for fetching cycle counts only when classifying
			if ((mButtonLearn.value != iLearn), {
				var nCluster, cycles;
				nCluster = mCurrentCluster + 1;
				cycles = data.vrp.layers[\ClustersPhon].mapData(nCluster).totalPuts;
				mClassifiedCounts.put(mCurrentCluster, cycles);
			});
		}, {
			mClassifiedCounts = cs.pointsInCluster;  // Also init this if mStarted.not
		});

		mResetNow = false;

		if (mStarted.not and: data.general.started, {

			if (data.settings.io.keepData.not, { mClassifiedCounts = 0 ! cs.nClusters } );

			// Just started the server - so forcibly disable all input controls except reset
			[
				mNumberBoxClusters,
				mButtonInit,
				mButtonLearn,
				mButtonLoad,
				mButtonSave
			]
			do: { | x | x.enabled_(false); };

			// Arm the Auto Reset mechanism
			if (cs.autoReset,
				{
					mCountDownFrames = cs.iFramesToReset;
					mFramesWaited = 0;
				}
			);

			// Reset the mStatsHeight
			mStatsHeight = nDefaultStatsHeight;

		});

		if (mStarted and: { data.general.started.not }, {
			// Just stopped the server
			cd.resetNow = false; // It shouldn't matter leaving it as true, but we do this for safety.
			mButtonLoad.value_(iUnload); // Have data since we just stopped the server
			mButtonSave.setPostfix(if (mButtonLearn.value == iLearn, "*", ""));
			if (csg.clusterSortRequested and: { mButtonInit.value == iRelearn },
				{
					bSortRequested = true;
					VRPData.breatheCycles(1);
				}
			);
		});

		mStarted = data.general.started;
		this.updateMenu;
		mViewClusterCentroids.refresh;
		mViewClusterStats.refresh;
	} /* updateData */


	//// Drawing functions ///////////////

	drawCentroids { | view |
		var seq;
		var rc = view.bounds;
		var ptOrigin = rc.width.half@rc.height.half;
		var gridGreen = Color.new(0.0, 0.75, 0.3);
		var posLabels, posValues, spokeLength, spokeCount;
		var mFontSpokes = VRPViewMain.qtFont;


		spokeCount = mClusterMetrics.size;
		spokeLength = min(rc.width.half, rc.height.half) - 20;
		posLabels = Array.fill(spokeCount, { | i |
			var angle, x, y, rotate;
			rotate = i.neg; // if (spokeCount.odd, i, i+0.5);
			angle = (rotate/spokeCount+0.25)*2pi;
			x = ptOrigin.x + ((spokeLength+15)*cos(angle));
			y = ptOrigin.y - ((spokeLength+15)*sin(angle));
			Point.new(x, y)
		});

		Pen.use {
			var angle = 2pi/spokeCount;
			var start = -0.5pi;

			// Draw the spokes and perimeter of the polar grid
			Pen.strokeColor_(gridGreen);
			spokeCount do: { | i |
				Pen.addWedge(ptOrigin, spokeLength, i*angle + start, angle);
				Pen.stroke
			};

			// Draw a concentric circle at half the radius
			Pen.addArc(ptOrigin, spokeLength.half, 0, 2pi);
			Pen.stroke;

			// Draw the metric name labels
			Pen.fillColor_(Color.gray(0.25));
			posLabels do: { arg pt, m;
				var str = mClusterMetrics[m].asString;
				var rc = str.bounds(mFontSpokes).resizeBy(2, 2);
				rc = rc.moveToPoint(pt);
				rc = rc.moveBy(rc.width.half.neg, rc.height.half.neg);
				Pen.stringCenteredIn(str, rc, mFontSpokes, Color.gray(0.7));
			};
		};

		// Are we drawing all centroids (0) or just one (>0)?
		if (0 == mSelected, {
			seq = (0..(mNumberBoxClusters.value-1)).asInteger;

			seq.swap(mCurrentCluster, seq.last);  	// Draw the current centroid on top
		}, {
			seq = [mSelected - 1];
		});

		// Draw the sequence of centroids in the polar plot
		// ( and if the number of dimensions is less than 3, we may need a different plot... NYI )
		if (mClusterCentroids.size == mNumberBoxClusters.value, {
			// OK to go
			Pen.use {
				var angleStep, rotate1st;
				angleStep = 2pi/spokeCount.neg;
				rotate1st = 0.5pi; // if (spokeCount.even, { 0.5pi + (angleStep/2) }, 0.5pi);

				// Draw the polar plot lines
				seq do: { | k, ik |
					Pen.strokeColor = mPalette.(k);
					Pen.width_(if (ik == (seq.size-1), 4, 2));
					posValues = Array.fill(spokeCount+1, { | i |
						var x, y, spoke, angle;

						spoke = i mod: spokeCount;
						angle = rotate1st + (i * angleStep);
						x = ptOrigin.x + ((spokeLength * mClusterCentroids[ k ][ spoke ])*cos(angle));
						y = ptOrigin.y - ((spokeLength * mClusterCentroids[ k ][ spoke ])*sin(angle));
						x@y
					});
					posValues do: { | pt, i |
						if (i==0, { Pen.moveTo(pt) }, { Pen.lineTo(pt) });
					};
					Pen.stroke;
				}
			}
		}, {
			nil // wait until next refresh when mClusterCentroids has been updated from the GUI
		});
	} /* .drawCentroids */

	drawStats { | view |
		var rc, bounds, barWidth, max = 50;
		var str, counts;

		if ((mButtonLearn.value == iLearn) or: (mStarted.not), {
			if (mClusterCounts.notNil, {
				counts = mClusterCounts;
			})
		}, {
			counts = mClassifiedCounts;
		});

		if (counts.notNil, { max = counts.maxItem } );

		if (mNumberBoxClusters.hasFocus, {
			str = format(" Palette for % phonation type clusters", mNumberBoxClusters.value.asInteger);
			max = 50;
			counts = max ! mNumberBoxClusters.value;
			mStatsHeight = nDefaultStatsHeight;
		});

		str =  format("% cycles", mStatsHeight);
		if ((mButtonLearn.value == iDontLearn) and: (mButtonInit.value == iPrelearned),
			{
				if (mClusterSettingsPathName.notNil, {
					str = str ++ format(" - classifying using \"%\"", mClusterSettingsPathName.basename);
				})
			}
		);

		// Update the virtual height of the stats view
		while ( { mStatsHeight < max }, { mStatsHeight = mStatsHeight * 2; } );

		if (counts.notNil and: { counts.size == mNumberBoxClusters.value }, {
			bounds = view.bounds;
			rc = Rect();
			barWidth = bounds.width / mNumberBoxClusters.value;
			Pen.use{
				mNumberBoxClusters.value.do ({ | i |
					var xPix, yPix, count;
					count = counts[i];
					xPix = i.linlin(0, mNumberBoxClusters.value, 0, bounds.width);
					yPix = count.linlin(0, mStatsHeight, 0, bounds.height);
					rc.set(xPix, bounds.height - yPix, barWidth, yPix);
					Pen.fillColor = mPalette.(i);
					Pen.fillRect(rc);
				});
				str.drawAtPoint(1@1, mFont, Color.yellow(0.7));
			};
		});
	}

	close {
		mButtonSave.removeUniqueMethods;
		this.release;
	}
}

