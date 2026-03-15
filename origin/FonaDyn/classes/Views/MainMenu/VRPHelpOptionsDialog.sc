// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

VRPHelpOptionsDialog {
	var mDialog, mView;
	var mStaticTextProgramVersion;
	var mStaticTextProgramLicence;
	var mStaticTextReadHandbook;
	var mCheckBoxOnscreenHelp;
	var mCheckBoxSonicAlerts;
	var mStaticTextLinks;
	var mStaticTextUsersForum;
	var mStaticTextOpenHelpDoc;
	var mStaticTextOpenHelpKeys;
	var mStaticTextCheckUpdates;
	var mGroupsIOFonaDyn = "https://voicemapping.groups.io/g/fonadyn";
	var mGroupsIOhandbook = "https://voicemapping.groups.io/g/fonadyn/files/FonaDyn%20Handbook%20%28latest%29.pdf";
	var mStensProfilePage = "https://www.kth.se/profile/stern";
	var mButtonOK, mButtonCancel;
	var urlHelp;

	*new { | parentMenu |
		^super.new.init(parentMenu);
	}

	init { | parentMenu |
		var static_font = VRPViewMain.staticFont;
		var button_font = VRPViewMain.qtFont;

		// Don't open if it is already present
		if (~fdHelpDialog.notNil, {
			mDialog = ~fdHelpDialog;
			mDialog.front;
			^true
		});

		urlHelp = PathName(\FonaDyn.asClass.filenameSymbol.asString).pathOnly +/+ "HelpSource/Reference";

		mDialog = Window.new("FonaDyn Help Options" /*, resizable: false */);
		mDialog.alwaysOnTop_(true);
		~fdHelpDialog = mDialog;
		mView = mDialog.view;
		mView.background_( Color(0.9, 0.9, 1.0) );
		mView.font_(static_font);

		mStaticTextProgramVersion
		= StaticText.new(mView, Rect())
		.string_("You are running version" + VRPMain.mVersion.asString)
		.align_(\right);
		mStaticTextProgramVersion.font_(VRPViewMain.qtFont);

		mCheckBoxOnscreenHelp
		= CheckBox(mView, Rect(), "On-screen help tips - just point")
		.font_(static_font)
		.setProperty(\toolTip, "Toggle the help tips on/off with key F1" )
		.value_(~bShowToolTips)
		.action_( { | cb | ~bShowToolTips = cb.value } );

		mCheckBoxSonicAlerts
		= CheckBox(mView, Rect(), "Sonic alerts: pling, klunk, or alarm bell.")
		.font_(static_font)
		.setProperty(\toolTip, "Check the Post window to see what happened.\nToggle sonic alerts on/off with key F4." )
		.value_(VRPViewMain.bSonicAlerts)
		.action_( { | cb | VRPViewMain.bSonicAlerts = cb.value } );

		mStaticTextLinks
		= StaticText.new(mView, Rect())
		.font_(VRPViewMain.qtFont)
		.string_("LINKS:");

		mStaticTextOpenHelpKeys
		= StaticText.new(mView, Rect())
		.font_(VRPViewMain.qtFont)
		.string_("Shortcut keys" )
		.stringColor_(Color.blue(0.4));
		mStaticTextOpenHelpKeys
		.setProperty(\toolTip, "Help Browser, topic 'FonaDyn > FonaDyn Shortcuts'" )
		.mouseDownAction_( {
			HelpBrowser.openHelpFor("FonaDyn Shortcuts");
		});

		mStaticTextReadHandbook
		= StaticText.new(mView, Rect())
		.font_(VRPViewMain.qtFont)
		.string_("The FonaDyn Handbook (latest version)")
		.stringColor_(Color.blue(0.4));
		mStaticTextReadHandbook
		.setProperty(\toolTip, "To access the Handbook: join the forum,\nor find the PDF in the distribution folder." )
		.mouseDownAction_( { mGroupsIOhandbook.openOS } );  // URL of user group forum

		mStaticTextUsersForum
		= StaticText.new(mView, Rect())
		.font_(VRPViewMain.qtFont)
		.string_("FonaDyn Users Group - join, and ask anything" )
		.stringColor_(Color.blue(0.4));
		mStaticTextUsersForum
		.setProperty(\toolTip, mGroupsIOFonaDyn )
		.mouseDownAction_( { mGroupsIOFonaDyn.openOS } );  // URL of user group forum

		mStaticTextOpenHelpDoc
		= StaticText.new(mView, Rect())
		.font_(VRPViewMain.qtFont)
		.string_("FonaDyn help for programmers" )
		.stringColor_(Color.blue(0.4));
		mStaticTextOpenHelpDoc
		.setProperty(\toolTip, "Help Browser topic 'FonaDyn'" )
		.mouseDownAction_( { HelpBrowser.openBrowsePage("FonaDyn") } );  // SC internal Help system

		mStaticTextCheckUpdates
		= StaticText.new(mView, Rect())
		.font_(VRPViewMain.qtFont)
		.string_("Check for updates" )
		.stringColor_(Color.blue(0.4));
		mStaticTextCheckUpdates
		.setProperty(\toolTip, mStensProfilePage )
		.mouseDownAction_( { mStensProfilePage.openOS } );  // Sten's profile page

		mStaticTextProgramLicence
		= StaticText.new(mView, Rect())
		.font_(VRPViewMain.qtFont)
		.string_("License: distributed under EUPL v1.2.\n(click to read)" )
		.align_(\left)
		.stringColor_(Color.blue(0.4));
		mStaticTextProgramLicence
		.setProperty(\toolTip, ~gLicenceLink )
		.fixedSize_(mStaticTextProgramLicence.sizeHint)
		.mouseDownAction_( { ~gLicenceLink.openOS } );  // global link defined in VRPMain.sc

		mButtonOK
		= Button(mView, Rect())
		.font_(button_font)
		.states_([["Close"]])
		.action_( { mDialog.close });

		mView.allChildren( { |v|
			if (v.class == StaticText, { v.minWidth_(360); v.fixedHeight_(45) });
		});

		mStaticTextProgramVersion
		.font_(button_font)
		.fixedWidth_(180);

		mView.keyDownAction_({ | view, char |
			case
			{char == 27.asAscii} { mDialog.close; true }	// Escape: Cancel
			{char == 13.asAscii} { mDialog.close; true }	// Enter:  OK
			{ false }
		});

		mView.layout = VLayout.new(
			[20, s:2],
			[mCheckBoxOnscreenHelp, s: 1],
			[mCheckBoxSonicAlerts, s: 1],
			[nil, s:2],
			[mStaticTextLinks, s: 1],
			[mStaticTextOpenHelpKeys, s:1],
			[mStaticTextReadHandbook, s: 1],
			[mStaticTextUsersForum, s: 1],
			HLayout([mStaticTextCheckUpdates, s: 1], nil, [mStaticTextProgramVersion, s:1]),
			[mStaticTextOpenHelpDoc, s: 1],
			[nil, s:2],
			HLayout(
				[mStaticTextProgramLicence, stretch: 1, align: \left],
				[nil, s:3],
				[mButtonOK, a: \right]
			)
		);

		mView.layout.margins_(15);
		mDialog.front;
		mDialog.onClose_( { ~fdHelpDialog = nil } );

	} /* init */

}