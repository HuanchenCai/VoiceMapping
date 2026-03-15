//// Color map testing script //////////////////////////////////

(
w = Window.new(bounds: Rect(10, 200, 450, 80));
w.front;
w.background_(Color.white);
r = Rect(10, 10, 360, 50);
u = UserView(w, r);
d = thisProcess.platform.userExtensionDir +/+ "FonaDynTools/colormaps";
f = "IBM5.csv";
w.name_(f);
t = Font.new("Arial", bold: true, size: 12);

u.drawFunc_{
	var c = 5;
	var palStr;
	m = ColorMap.new();
	m.load(d +/+ f, true);
	p = m.smoothPaletteFunc;
	palStr = ", smooth palette";
	// p = m.steppedPaletteFunc(c);
	// palStr = ", stepped palette";
	Pen.use {
		var nColors = r.width.half;
		var pos, rc, offs = 0;
		nColors.do ({ |k|
			rc = Rect(r.left+(k*2), r.top, 3, r.height) & r;
			pos = k / nColors.asFloat;
			// pos = (pos*(c)).floor/(c); // uncomment for stepped palette
			Pen.color = p.(pos);
			Pen.addRect(rc);
			Pen.fill;
		});
		Pen.stringLeftJustIn(" " + f ++ palStr, r, t, Color.white);
	};
};

u.refresh;
)


//// Color array listing - set f to the filename  /////////////////////

(
	var window, tree, colormap, colors, filepath;

	f = "PaulTolsMuted8.csv";

	window = Window.new(f).front;
	window.view.layout_(VLayout(
		tree = TreeView();
	));
	tree.columns_(["Index", "Colour", "Red", "Green", "Blue"]);
	tree.font = Font.new("Arial", bold: true, size: 12);
	[50, 100, 60, 60, 60].do { | w, ix | tree.setColumnWidth(ix, w) };

	filepath = thisProcess.platform.userExtensionDir +/+ "FonaDynTools/colormaps" +/+ f;
	colormap = ColorMap.new();
	colormap.load(filepath, true);

	colors = [];
	colormap.colorArray.do { | triplet, i|
		colors = colors.add(Color.fromArray(triplet));
		tree.addItem( [i, " ", triplet[0], triplet[1], triplet[2]] );
	};

	tree.numItems.do{ |i|
		var c = [Color.clear, colors[i], Color.clear, Color.clear];
		tree.itemAt(i).colors_(c).textColors_(Color.grey);
	};

	tree.onItemChanged_({ |view|
		view.currentItem.strings.postln;
	});

)



