// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

VRPViewMain {
	// Views
	var mView;

	var mViewMenu;
	var mVRPViewMenu;

	var mViewSampEn;
	var mVRPViewSampEn;

	var mViewCluster;
	var mVRPViewCluster;

	var mViewClusterPhon;
	var mVRPViewClusterPhon;

	var mViewVRP;
	var mVRPViewVRP;

	var mViewPlayer;
	var mVRPViewPlayer;

	var mViewMovingEGG;
	var mVRPViewMovingEGG;

	// Context menu stuff
	var mMenuActionsArray;
	var mMenuContentsArray;
	var mContextMenu;
	var fnOnContextMenuOpen;

	// States
	var mStackLayout;
	var mCurrentLayout;
	var mCurrentStackType;
	var mReplayToggle;
	var mVisibles;
	var mMapsWidth;
	var bNewLayout;
	var bSonicAlertsInstance;
	var	bShowToolTipsInstance;

	// Layout types
	classvar <layoutGrid = 1;
	classvar <layoutGallery = 2;
	classvar <layoutStack = 3;
	classvar <layoutGridAll = 4;
	classvar <layoutGalleryAll = 5;

	classvar <stackTypeSampEn = 1;
	classvar <stackTypeClusterEGG = 2;
	classvar <stackTypeClusterPhon = 3;
	classvar <stackTypeVRP = 4;
	classvar <stackTypeMovingEGG = 5;
	classvar <stackTypeSignal = 6;

	// Alert sounds
	classvar <>bSonicAlerts = false;
	classvar <warnSound;
	classvar <errorSound;
	classvar <helpSound;

	// GUI
	classvar <staticFont;
	classvar <qtFont;
	classvar <gridFont;

	*new { | view |
		^super.new.init(view);
	}

	*configureSoundAlerts { arg sonic=nil;
		if (sonic.isNil, { ^nil } );
		bSonicAlerts = sonic;
		if (sonic, {
			warnSound  = { Synth.new(\FonaDynBonk,  addAction: \addToHead) };
			errorSound = { Synth.new(\FonaDynCrash, addAction: \addToHead) };
			helpSound  = { Synth.new(\FonaDynHelp,  addAction: \addToHead) };
			"Sonic alerts are activated.".postln;
		}, {
			warnSound  = { };
			errorSound = { };
			helpSound  = { };
			"Sonic alerts are deactivated.".postln;
		});
	}


	//////  FOR DEBUGGING ONLY: KEY F9 /////////////////////////////////////////////
	//////  Shows the layout of all child views: visible in green, invisible in blue
	////////////////////////////////////////////////////////////////////////////////

	mapAll { arg topView;
		var v, vRect, screenRect, topRect;

		topRect = topView.absoluteBounds;
		vRect = (topRect.asArray * 0.5).asRect.moveTo(600, 400);
		v = View(nil, vRect);
		if (topView.children.isEmpty.not, { this.mapChildren(v, topView) });
		v.front;
	}

	mapChildren { arg frameView, parentView;
		parentView.children do: { arg cv;
			var cRect, ch;
			cRect = (cv.bounds.asArray * 0.5).asRect;
			ch = StaticText.new(frameView, cRect);
			ch.background_(if (cv.visible, Color(0, 0.7, 0, 0.25), Color(0, 0, 0.7, 0.25)));
			if (cv.children.isEmpty.not, { this.mapChildren(ch, cv) });
		};
	}

	////////////////////////////////////////////////////////////////////////////////
	// CONTEXT-SENSITIVE HELP
	////////////////////////////////////////////////////////////////////////////////

	setToolTips { arg topView, bShow;
		if (bShow.not, {
			// Turn them off
			topView.allChildren.do { |v|
				v.setProperty(\toolTip, nil);
			};
			"On-screen help is hidden.".postln;
			warnSound.value;
		}, {
			// Turn them on
			topView.allChildren.do { |v|
				v.setProperty(\toolTip, v.getProperty(\contextHelp));
			};
			"On-screen help is active.".postln;
			helpSound.value;
		});
		^bShow
	}

	////////////////////////////////////////////////////////////////////////////////

	initFonts {
		Platform.case
		{ \osx } {
			// usePointSize does not work on MacOS
			var sz = (Window.screenBounds.height.sqrt/2.75).round(1);
			staticFont = Font.new("Arial", sz);
			qtFont = Font.new("Arial", sz, bold: true);
			gridFont = Font.new("Arial", (sz * 0.9).round(1));
		}
		{
			staticFont = Font.new("Arial", 10, bold: false, usePointSize: true);
			qtFont = Font.new("Arial", 9, bold: true, usePointSize: true);
			gridFont = Font.new("Arial", 8.5, usePointSize: true);
		};
	}

	init { | view |
		var rcTmp;

		mView = view;
		~bShowToolTips = false;
		bShowToolTipsInstance = ~bShowToolTips;
		bSonicAlertsInstance = bSonicAlerts;
		mReplayToggle = false;
		this.initFonts;

		// Create the views and menu
		mViewMenu = CompositeView(mView, mView.bounds);
		mViewPlayer = CompositeView(mView, mView.bounds);
		mViewSampEn = CompositeView(mView, mView.bounds);
		mViewMovingEGG = CompositeView(mView, mView.bounds);
		mViewVRP = CompositeView(mView, mView.bounds);
		mViewCluster = CompositeView(mView, mView.bounds);
		mViewClusterPhon = CompositeView(mView, mView.bounds);

		// Init the subobjects
		mVRPViewSampEn = VRPViewPlots( mViewSampEn );
		mVRPViewPlayer = VRPViewPlayer ( mViewPlayer );
		// mVRPViewVRP = VRPViewVRP( mViewVRP );  // when supporting only a single map view
		mVRPViewVRP = VRPViewMaps( mViewVRP );		// when supporting multiple map views
		mVRPViewCluster = VRPViewCluster( mViewCluster );
		mVRPViewClusterPhon = VRPViewClusterPhon( mViewClusterPhon );
		// mVRPViewSampEn = VRPViewSampEn( mViewSampEn );    /////////////
		mVRPViewMovingEGG = VRPViewMovingEGG( mViewMovingEGG );
		mVRPViewMenu = VRPViewMainMenu( mViewMenu );

		this.createContextMenu(mView);

		// Fix the layout - so the subobjects know their sizes
		mStackLayout = nil;
		mCurrentLayout = layoutStack;
		mCurrentStackType = stackTypeVRP;
		this.setLayout(layoutStack);
		// Actually this setting is promptly overridden by VRPViewMainMenuGeneral:Show

		// Press Alt + one of c|f|v|m|p|t|b|d|s|l|h to toggle the visibility of any graph
		mView.keyDownAction_({ arg v, c, mods, u, kCode, k;
			var bHandled = true;
			var playKeys = [32] ++ (49..57);  // will play also when a number key is pressed

			// F1 for Help, F2 for START, F3 for PAUSE
			// F4 for sonic alerts on/off, F5 for 2xReset,
			// F6 to plot the chosen metrics for the selected signal
			// F9 for window debugging
			// "http://qt-project.org/doc/qt-4.8/qt.html#Key-enum"
			switch (k,
				16r01000030, { ~bShowToolTips = this.setToolTips(mView, bShowToolTipsInstance = ~bShowToolTips.not) },
				16r01000031, { mVRPViewMenu.start },
				16r01000032, { mVRPViewMenu.pause },
				16r01000033, { this.class.configureSoundAlerts(bSonicAlertsInstance = bSonicAlerts.not) },
				16r01000034, { mVRPViewCluster.pressReset; mVRPViewClusterPhon.pressReset },
				16r01000035, { mVRPViewPlayer.requestPlot },
				16r01000038, { this.mapAll(mView) },  //// FOR DEBUGGING ONLY
				{ bHandled = false }
			);

			if (playKeys.includes(k), {
				mReplayToggle = true;
			});

			if ((c.toLower > $a) and: (mods.isAlt), {
				switch (c.toLower,
					$c, {
						mViewCluster.visible_(mViewCluster.visible.not);
					},
					$f, {
						mViewClusterPhon.visible_(mViewClusterPhon.visible.not);
					},
					$v, {
						mViewVRP.visible_(mViewVRP.visible.not);
					},
					$t, {
						mVRPViewVRP.toggleMap(if (mods.isShift) { VRPViewVRP.iCloneFloat } { VRPViewVRP.iClone } );
					},
					$b, {
						mVRPViewVRP.toggleMap(VRPViewVRP.iReference);
					},
					$d, {
						mVRPViewVRP.toggleMap(VRPViewVRP.iDiff);
					},
					$s, {
						mVRPViewVRP.toggleMap(VRPViewVRP.iSmooth);
					},
					$m, {
						if (mods.isShift, {
							mVRPViewMovingEGG.cloneFloat;
						} , {
							mViewMovingEGG.visible_(mViewMovingEGG.visible.not);
						});
					},
					$p, {
						mViewSampEn.visible_(mViewSampEn.visible.not);
					},
					$l, {
						mVRPViewPlayer.toggleVisible;
					},
					$h, {
						mVRPViewMenu.toggleHeight;
					},
					$x, {
						mVRPViewVRP.toggleLayout;  // tiled maps horz or vert
					}
				);
			});
			bHandled
		});

		mView.mouseDownAction_({ arg v, x, y, mods, btn, clickCount;
			if ((btn == 1) and: { clickCount == 1 },
				{ mContextMenu.front }
		)});

		mVisibles = this.viewsArray collect: { |v| true };
		mMapsWidth = 1;
		mView.allChildren.do { |v|
			v.setProperty(\toolTip, nil);
		};
	} /* .init */

	vrpViewsArray {
		^[
			mVRPViewMenu,
			mVRPViewSampEn,
			mVRPViewMovingEGG,
			mVRPViewCluster,
			mVRPViewClusterPhon,
			mVRPViewVRP,
			mVRPViewPlayer		// must be last
		];
	}

	viewsArray {
		^[
			mViewSampEn,
			mViewMovingEGG,
			mViewVRP,
			mViewCluster,
			mViewClusterPhon
		];
	}

	createContextMenu { | view |
		mMenuActionsArray = [];
		// Since this is a separate Menu, and not shortcuts added to a context menu of the View,
		// the shortcut keys in col[1] have to be implemented with keyDownAction, as above;
		// but we display them here to help the user.
		// On the Mac, the shortcuts do not show up in the menu (a bug in Qt?).
		mMenuContentsArray = [
			["Show/hide graphs", \separator],
			["Compact top", "Alt+H", { |a, bChecked | mVRPViewMenu.compactHeight(bChecked) } ],
			["Moving EGG",  "Alt+M", { |a, bChecked | mViewMovingEGG.visible_(bChecked) } ],
			["Time Plots",  "Alt+P", { |a, bChecked | mViewSampEn.visible_(bChecked) } ],
			["Signal",  "Alt+L", { |a, bChecked | a.checked_(mVRPViewPlayer.toggleVisible.not) }],   //// needs checking
			["EGG waveshape clusters",  "Alt+C", { |a, bChecked | mViewCluster.visible_(bChecked) } ],
			["Phonation type clusters", "Alt+F", { |a, bChecked | mViewClusterPhon.visible_(bChecked) } ],
			["Voice Map",  "Alt+V", { |a, bChecked | mViewVRP.visible_(bChecked) }],
			["Extra maps", \separator],
			["Participant map", "Shift+Alt+T", { | a | a.checked_(mVRPViewVRP.toggleMap(VRPViewVRP.iCloneFloat)) }],
			["Twin", "Alt+T",   { | a | a.checked_(mVRPViewVRP.toggleMap(VRPViewVRP.iClone)) }],
			["Before", "Alt+B", { | a | a.checked_(mVRPViewVRP.toggleMap(VRPViewVRP.iReference)) }],
			["Difference", "Alt+D",   { | a | a.checked_(mVRPViewVRP.toggleMap(VRPViewVRP.iDiff)) }],
			["Smooth", "Alt+S", { | a | a.checked_(mVRPViewVRP.toggleMap(VRPViewVRP.iSmooth)) } ]
		];

		mMenuContentsArray do: { | desc, i |
			var next;
			if (desc[1] == \separator,
				{
					next = MenuAction.separator(desc[0])
				}, {
					next = MenuAction.new(desc[0], desc[2]);
					next.shortcut = desc[1];
					next.checkable = true;
				}
			);
			mMenuActionsArray = mMenuActionsArray.add(next);
		};
		mContextMenu = Menu.new( *mMenuActionsArray[(0..mMenuActionsArray.size-1)] );

		fnOnContextMenuOpen = { arg menu, what, value;
			this.updateContextMenu(menu, what, value)
		};
		mContextMenu.addDependant( fnOnContextMenuOpen );
	} /* .createContextMenu */

	updateContextMenu { | menu, what, value |
		// The show/hide panels popup-menu is about to be shown.
		// We can't rely on tracking the MenuAction states,
		// because .visible_() is called also from the main layouting and the Alt-keys
		if (what == \aboutToShow, {
			              // [ 0] is a separator
			mMenuActionsArray[ 1].checked_(mVRPViewMenu.visible.not);  	// inquires the hosting object
			mMenuActionsArray[ 2].checked_(mViewMovingEGG.visible);		// inquires the view directly
			mMenuActionsArray[ 3].checked_(mViewSampEn.visible);
			mMenuActionsArray[ 4].checked_(mVRPViewPlayer.bHiddenByUser.not);
			mMenuActionsArray[ 4].enabled_(VRPDataPlayer.enabled);
			mMenuActionsArray[ 5].checked_(mViewCluster.visible);
			mMenuActionsArray[ 6].checked_(mViewClusterPhon.visible);
			mMenuActionsArray[ 7].checked_(mViewVRP.visible);
			              // [ 8] is a separator
			mMenuActionsArray[ 9].checked_(mVRPViewVRP.mapIndex( VRPViewVRP.iCloneFloat ).notNil); // ask the maps manager
			mMenuActionsArray[10].checked_(mVRPViewVRP.mapIndex( VRPViewVRP.iClone ).notNil);
			mMenuActionsArray[11].checked_(mVRPViewVRP.mapIndex( VRPViewVRP.iReference ).notNil);
			mMenuActionsArray[12].checked_(mVRPViewVRP.mapIndex( VRPViewVRP.iDiff ).notNil);
			mMenuActionsArray[13].checked_(mVRPViewVRP.mapIndex( VRPViewVRP.iSmooth ).notNil);
		});
	} /* .updateContextMenu */

	setLayout { | l |
		mView.layout_(
			this.doLayout(
				l,
				mViewMenu,
				mViewVRP,
				mViewCluster,
				mViewClusterPhon,
				mViewSampEn,
				mViewMovingEGG,
				mViewPlayer
			)
		);
		mView.layout.margins_(5);

		mCurrentLayout = l;
		bNewLayout = false;
		mView.setProperty(\contextHelp, "Some fields have help texts.\nPress F1 and point to anything to find out.");
		mView.refresh;
	} /* .setLayout */

	doLayout { | type, menu, vrp, cluster, clusterPhon, sampen, movingEGG, player |
		var resultLayout, graphsLayout;
		if ((type == layoutGridAll) or: (type == layoutGalleryAll), {
			this.viewsArray.do { |v| v.visible = true };
			type = type - 3;
		});

		graphsLayout = switch ( type,
			layoutGrid, { 			// GridLayout.rows didn't do what I want
				var g;
				g = VLayout(
					[player, stretch: 1],
					[HLayout(
						[VLayout(
							HLayout( [sampen, stretch: 1], [movingEGG, stretch: 1]),
							cluster,
							clusterPhon,
						), stretch: 1],
						[vrp, stretch: mMapsWidth]
					), stretch: 8],
				)
			},

			layoutGallery, {
				VLayout(
					[player, stretch: 2],
					[HLayout(cluster, movingEGG, sampen, clusterPhon), stretch: 3],
					[vrp, stretch: 4]
				)
			},

			layoutStack, {
				// Layout using a stack ("one graph"); but it sets all views to visible
				mStackLayout = StackLayout(
					vrp,
					cluster,
					clusterPhon,
					sampen,
					movingEGG,
					player
				);
				mStackLayout.mode_(\stackAll);
			}
		); // Force the top 'menu' to take up as little space as possible!

		resultLayout = VLayout(
			[menu, stretch: 1],
			[graphsLayout, stretch: 10]
		);
		^resultLayout
	}

	stash { | settings |
		settings.waitingForStash_(true);
	}

	fetch { | settings |
		var lo, st, resetLayout;

		this.vrpViewsArray
		do: { | x |
			x.fetch(settings);
		};

		// Change layout?
		lo = settings.general.layout;
		st = settings.general.stackType;
		if (lo != mCurrentLayout, { bNewLayout = true } );

		if (mStackLayout.notNil, { if (mCurrentStackType != st, { bNewLayout = true; }) });

		resetLayout = (lo < 0);		// if lo was negative, force all to visible
		lo = lo.abs;

		case
			// ENTER Key on Show unhides all graphs
			{ resetLayout }
				{ mVisibles = this.viewsArray collect: { |v| v.visible = true } }

			// Switching to One Graph or All: save visibilities
			{ (mCurrentLayout < layoutStack) and: (lo >= layoutStack) }
				{ mVisibles = this.viewsArray collect: { |v| v.visible } }

			// Switching to Tiled or Gallery: restore saved visibilities
			{ (mCurrentLayout >= layoutStack) and: (lo < layoutStack) }
				{ mVisibles do: { |b, ix| this.viewsArray[ix].visible_(b) } }
			;

		if ( bNewLayout, {
			this.setLayout(lo);
			if (layoutStack == lo, {
				mStackLayout.index = switch( st,
					VRPViewMain.stackTypeVRP, 0,
					VRPViewMain.stackTypeClusterEGG, 1,
					VRPViewMain.stackTypeClusterPhon, 2,
					VRPViewMain.stackTypeSampEn, 3,
					VRPViewMain.stackTypeMovingEGG, 4,
					VRPViewMain.stackTypeSignal, 5
				);
				mCurrentStackType = st;
			});
		});

		if (bSonicAlerts != bSonicAlertsInstance,
			{ // Alerts have been toggled from elsewhere
				this.class.configureSoundAlerts(bSonicAlertsInstance = bSonicAlerts);
			}
		);

		if (~bShowToolTips != bShowToolTipsInstance,
			{  // ToolTips have been toggled from elsewhere
				this.setToolTips(mView, bShowToolTipsInstance = ~bShowToolTips);
			}
		);

		^settings
	}

	updateData { | data |
		var dsg = data.settings.general;

		if (mMapsWidth != data.vrp.mapsWidth,
			{
			mMapsWidth = data.vrp.mapsWidth;
			bNewLayout = true;
			}
		);

		this.vrpViewsArray
		do: { | x |
			x.updateData(data);
		};

		if (dsg.guiChanged, {
			mView.background_(dsg.getThemeColor(\backDrop));
			dsg.guiChanged = false; // Now all windows have done it
		});

		if (mReplayToggle, {
			if (data.player.status == VRPDataPlayer.iStatusIdle, {
				data.player.markForReplay();
			}, {
				data.player.markForStop();
			});
			mReplayToggle = false;
		});
	}

	close {
		this.vrpViewsArray
		do: { | x |
			x.close;
		};
		mContextMenu.release;
	}
}

