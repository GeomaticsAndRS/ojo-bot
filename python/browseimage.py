#!/usr/bin/env python
#
# Created on 3/18/2014 Pat Cappelaere - Vightel Corporation
#
# Generates a BrowseImage using an OSM Map Background and superimposing the product
#
import os, inspect, socket
import sys, urllib, httplib
import math
import argparse
from osgeo import gdal
from osgeo import osr
from osgeo import ogr
import numpy

# timeout in seconds
timeout = 30
socket.setdefaulttimeout(timeout)

MAXZOOMLEVEL 		= 32

verbose = 0
force 	= 1

def execute( cmd ):
	if verbose:
		print cmd
	os.system(cmd)
	
#
# return a decimal tuple (r,g,b,255) from hex
#
def hex_to_rgb(value):
	value += "ff"	# for alpha
	value = value.lstrip('#')
	lv = len(value)
	return tuple(int(value[i:i + lv // 4], 16) for i in range(0, lv, lv // 4))

#	
# Code from gdal2tiles
#
tileSize 			= 256
initialResolution 	= 2 * math.pi * 6378137 / tileSize
# 156543.03392804062 for tileSize 256 pixels
originShift 		= 2 * math.pi * 6378137 / 2.0
# 20037508.342789244

def Resolution(zoom):
	return initialResolution / (2**zoom)
	
def LatLonToMeters( lat, lon ):
	"Converts given lat/lon in WGS84 Datum to XY in Spherical Mercator EPSG:900913"

	mx = lon * originShift / 180.0
	my = math.log( math.tan((90 + lat) * math.pi / 360.0 )) / (math.pi / 180.0)

	my = my * originShift / 180.0
	return mx, my

def MetersToLatLon( mx, my ):
	"Converts XY point from Spherical Mercator EPSG:900913 to lat/lon in WGS84 Datum"

	lon = (mx / originShift) * 180.0
	lat = (my / originShift) * 180.0

	lat = 180 / math.pi * (2 * math.atan(math.exp(lat * math.pi / 180.0)) - math.pi / 2.0)
	return lat, lon

def PixelsToMeters( px, py, zoom):
	"Converts pixel coordinates in given zoom level of pyramid to EPSG:900913"

	res = Resolution(zoom)
	mx = px * res - originShift
	my = py * res - originShift
	return mx, my

def MetersToPixels( mx, my, zoom):
	"Converts EPSG:900913 to pyramid pixel coordinates in given zoom level"

	res = Resolution( zoom )
	px = (mx + originShift) / res
	py = (my + originShift) / res
	return px, py

def ZoomForPixelSize( pixelSize ):
	"Maximal scaledown zoom of the pyramid closest to the pixelSize."

	for i in range(MAXZOOMLEVEL):
		if pixelSize > Resolution(i):
			if i!=0:
				return i-1
			else:
				return 0 # We don't want to scale up
#
# end of gdal2tiles code

def deg2tilenum( lat_deg, lon_deg, zoom):
	lat_rad = math.radians(lat_deg)
	n = 2.0 ** zoom
	xtile = int((lon_deg + 180.0) / 360.0 * n)
	ytile = int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
	print "deg2tilenum:", lat_deg, lon_deg, zoom, xtile, ytile
	return (xtile, ytile)
	
def tilenum2deg(xtile, ytile, zoom):
	n = 2.0 ** zoom
	lon_deg = xtile / n * 360.0 - 180.0
	lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
	lat_deg = math.degrees(lat_rad)
	print "tilenum2deg:", xtile, ytile, zoom, lat_deg, lon_deg
	return (lat_deg, lon_deg)

#
# Various way to generate a background image
#

def wms(ullat, ullon, lrlat, lrlon, osm_bg_image):
	width		= lrlon - ullon
	height		= ullat - lrlat
	
	if width < 0:
		width = -width
		
	if height < 0:
		height = -height
		
	# height/width has to be > 280
	minDim 	= min(width, height)
	ratio	=  280.0 / minDim
	width	= width * ratio
	height	= height * ratio
	
	#"http://129.206.228.72/cached/osm?LAYERS=osm_auto:all&STYLES=&SRS=EPSG:4326&FORMAT=image%2Fpng&SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&BBOX=-127.25,-50,180,50&WIDTH=922&HEIGHT=300"
	#"http://129.206.228.72/cached/osm?LAYERS=osm_auto:all&STYLES=&SRS=EPSG:4326&FORMAT=image%2Fpng&SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&BBOX=-127.25,-50,180,50&WIDTH=614&HEIGHT=200"

	#url 	= str.format("http://129.206.228.72/cached/osm?LAYERS=osm_auto:all&STYLES=&SRS=EPSG:4326&FORMAT=image%2Fpng&SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&BBOX={0},{1},{2},{3}&WIDTH={4}&HEIGHT={5}",ullon,lrlat,lrlon,ullat,int(width),int(height))
	if lrlat == -90:
		lrlat = -89.5
	if ullat == 90:
		ullat = 89.5
		
	url 	= str.format("http://ows.terrestris.de/osm/service?LAYERS=OSM-WMS&STYLES=&SRS=EPSG:4326&FORMAT=image%2Fpng&SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&BBOX={0},{1},{2},{3}&WIDTH={4}&HEIGHT={5}", ullon,lrlat,lrlon,ullat,int(width),int(height))
	
	# There is a bug on previous WMS for Central America
	url		= str.format("http://www2.demis.nl/worldmap/wms.asp?Service=WMS&Version=1.1.0&Request=GetMap&Layers=Countries,Borders,Coastlines&Format=image/png&SRS=EPSG:4326&BBOX={0},{1},{2},{3}&WIDTH={4}&HEIGHT={5}", ullon,lrlat,lrlon,ullat,int(width),int(height))
	
	#if verbose:
	print "wms url:" , url
	
	urllib.urlretrieve(url, osm_bg_image)
	
	#if verbose:
	print "created:" , osm_bg_image
		
		
# Using Mabox
#
def mapbox_image(centerlat, centerlon, z, rasterXSize, rasterYSize, osm_bg_image):
	global verbose
	
	#if verbose:
	#	print "outputbrowse_image", rasterXSize, rasterYSize, z, centerlat, centerlon
	
	if force or not os.path.isfile(osm_bg_image):	
		mapbox_url = str.format("http://api.tiles.mapbox.com/v3/cappelaere.map-1d8e1acq/{0},{1},{2}/{3}x{4}.png32",centerlon, centerlat, z, rasterXSize,rasterYSize)

		if verbose:
			print "wms url:" , mapbox_url, verbose
	
		urllib.urlretrieve(mapbox_url, osm_bg_image)
		if verbose:
			print "created:" , osm_bg_image, verbose


# Using Mapquest bbox... but does not seem to be accurate
#
def mapquest_image(ullat, ullon, lrlat, lrlon, zoom, width, heigth, osm_bg_image):
	url 		= "http://www.mapquestapi.com/staticmap/v4/getmap?key=Fmjtd%7Cluur2luy25%2C82%3Do5-9a7nq4"
	bestfit		= str.format("&bestfit={0},{1},{2},{3}", ullat, ullon, lrlat, lrlon)
	size		= str.format("&size={0},{1}", width, heigth)
	zoom		= str.format("&zoom={0}", zoom)
	margin		= str.format("&margin=1")
	imagetype 	= str.format("&imagetype=png")
	
	url += bestfit
	url += size
	url += zoom
	url += margin 
	url += imagetype
	
	if verbose:
		print "mapquest url:" , url
		
	urllib.urlretrieve(url, osm_bg_image)

	if verbose:
		print "created:" , osm_bg_image

# Using Mapquest static map center latlon and zoom level
#
def mapquest_center_image(lat, lon, zoom, width, heigth, osm_bg_image):
	url 		= "http://www.mapquestapi.com/staticmap/v4/getmap?key=Fmjtd%7Cluur2luy25%2C82%3Do5-9a7nq4"
	center		= str.format("&center={0},{1}", lat, lon )
	size		= str.format("&size={0},{1}", width, heigth)
	zoom		= str.format("&zoom={0}", zoom)
	margin		= str.format("&margin=0")
	imagetype 	= str.format("&imagetype=png")
	
	url += center
	url += size
	url += zoom
	# url += margin 
	url += imagetype
	
	if verbose:
		print "mapquest url:" , url
		
	urllib.urlretrieve(url, osm_bg_image)

	if verbose:
		print "created:" , osm_bg_image

# Using Google static maps
#	
def google_center_image(lat, lon, zoom, width, heigth, osm_bg_image):
	url 		= "https://maps.googleapis.com/maps/api/staticmap?"
	center		= str.format("&center={0},{1}", lat, lon )
	size		= str.format("&size={0}x{1}", width, heigth)
	zoom		= str.format("&zoom={0}", zoom)
	sensor		= str.format("&sensor=false")
	#margin		= str.format("&margin=0")
	#imagetype 	= str.format("&imagetype=png")
	
	url += center
	url += size
	url += zoom
	url += sensor
	#url += imagetype
	
	if verbose:
		print "google url:" , url
		
	urllib.urlretrieve(url, osm_bg_image)

	if verbose:
		print "created:" , osm_bg_image
		

#	
# Generate the BBOX for that center latlon and zoom level
#
def Gen_bbox(lat, lon, zoom, width, height):	
	mx, my 	= LatLonToMeters( lat, lon )
	
	px, py 	= MetersToPixels( mx, my, zoom)

	mx,my 	= PixelsToMeters( px - width/2, py + height/2, zoom)
	ullat, ullon = MetersToLatLon( mx, my )
	
	mx,my = PixelsToMeters( px + width/2, py - height/2, zoom)
	lrlat, lrlon = MetersToLatLon( mx, my )
		
	if ullon < -180:
		ullon = -180
		
	if lrlon > 180:
		lrlon = 180
		
	return ullon, ullat, lrlon, lrlat

#
# browse_filename is a tiff with color scheme derived from ds with colors
#
def	MakeBrowseImage(src_ds, browse_filename, subset_filename, osm_bg_image, sw_osm_image, levels, hexColors, _force, _verbose, zoom=4, scale=1, bbox=[], nodata=None):
	global force, verbose
	
	verbose = _verbose
	force	= _force
	
	assert( len(levels) == len(hexColors))
	if verbose:
		print "MakeBrowseImage verbose", verbose, subset_filename
	
	decColors = []
	for h in hexColors:
		rgb = hex_to_rgb(h)
		decColors.append(rgb)
		
	projection  		= src_ds.GetProjection()
	geotransform		= src_ds.GetGeoTransform()
	band				= src_ds.GetRasterBand(1)
	data				= band.ReadAsArray(0, 0, src_ds.RasterXSize, src_ds.RasterYSize )
	
	if nodata:
		data[data==nodata] = 0
		
	if scale != 1:
		if verbose:
			print "rescale for browse", scale
		data *= scale
	
	#print geotransform
	
	xorg				= geotransform[0]
	yorg  				= geotransform[3]

	xmax				= xorg + geotransform[1]* src_ds.RasterXSize
	ymax				= yorg + geotransform[5]* src_ds.RasterYSize
	
	if verbose:
		print "original coords", xorg, xmax, yorg, ymax
		
	deltaX				= xmax - xorg
	deltaY				= ymax - yorg
	
	driver 				= gdal.GetDriverByName( "GTiff" )
	
	if force or not os.path.isfile(browse_filename):	
		dst_ds_dataset	= driver.Create( browse_filename, src_ds.RasterXSize, src_ds.RasterYSize, 2, gdal.GDT_Byte, [ 'COMPRESS=DEFLATE', 'PHOTOMETRIC=MINISBLACK','ALPHA=YES' ] )

		# Levels are in reverse order, higher first
		# so let's reverse this
		rlist		= list(reversed(levels))
		
		firstItem 	= rlist.pop(0)
		lastItem 	= rlist.pop()
		
		if verbose:
			print "data <", firstItem, "= 0"
		
		data[data < firstItem]	= 0
		idx 					= -1
		l						= firstItem
		
		for idx, l in enumerate(rlist):
			if verbose:
				print "data >", firstItem, " and data <=", l, "=", idx+1
			
			data[numpy.logical_and(data>=firstItem, data<l)]= idx+1
			firstItem = l
			
		idx += 2

		#if verbose:
		#	print "data >", l, " and data <", lastItem, "=", idx
		#	print "data >=", lastItem, "=", idx+1

		data[numpy.logical_and(data>=l, data<lastItem)]		= idx
		data[data>=lastItem]								= idx+1
		
		o_band		 		= dst_ds_dataset.GetRasterBand(1)
		o_band.WriteArray(data.astype('i1'), 0, 0)

		a_band		 		= dst_ds_dataset.GetRasterBand(2)
		data[data > 0]		= 255
		data[data < 0]		= 0
	
		a_band.WriteArray(data.astype('i1'), 0, 0)
		
		ct = gdal.ColorTable()
		for i in range(256):
			ct.SetColorEntry( i, (0, 0, 0, 0) )
		
		decColors 	= list(reversed(decColors))
		for idx,d in enumerate(decColors):
			ct.SetColorEntry( idx+1, decColors[idx] )
			if verbose:
				print "Set BrowseImage ColorEntry", idx+1, decColors[idx]
	
		#try:
		o_band.SetRasterColorTable(ct)	# Seems to cause a TIFF ERROR  Cannot modify tag "PhotometricInterpretation" while writing
			
		o_band.SetNoDataValue(0)
	
		dst_ds_dataset.SetGeoTransform( geotransform )
		dst_ds_dataset.SetProjection( projection )
		
		dst_ds_dataset 	= None
		#except Exception as e:
		#	print "*** caught", e
		#	pass

		if verbose:
			print "Created Browse Image:", browse_filename
	
	# 
	centerlon		= (xorg + xmax)/2
	centerlat		= (yorg + ymax)/2
	#zoom			= 4
	
	if verbose:
		print "center target", centerlon, centerlat, zoom
		
	# Check raster size - thumbnail should be about width > 280 or more
	minDim 	= min(src_ds.RasterXSize, src_ds.RasterYSize)
	ratio	=  280.0 / minDim

	if ratio >= 1:
		ratio = round(ratio)+1	# round up

	
	rasterXSize = int(src_ds.RasterXSize*ratio)
	rasterYSize = int(src_ds.RasterYSize*ratio)
	
	if verbose:
		print "** Adjust", src_ds.RasterXSize, src_ds.RasterYSize, ratio, minDim, rasterXSize, rasterYSize, zoom, bbox
		
	#if len(bbox) == 0:
	#	if force or not os.path.isfile(osm_bg_image):
	#		print "** not", osm_bg_image
	#		mapbox_image(centerlat, centerlon, zoom, rasterXSize, rasterYSize, osm_bg_image)
	#	else:
	#		print "found", osm_bg_image
			
	#	ullon, ullat, lrlon, lrlat = Gen_bbox(centerlat, centerlon, zoom, rasterXSize, rasterYSize)
	
	#else:
	#	ullon = bbox[0]
	#	ullat = bbox[1]
	#	lrlon = bbox[2]
	#	lrlat = bbox[3]

	ullon = xorg
	ullat = yorg
	lrlon = xmax
	lrlat = ymax
	
	if verbose:
		print "mapbbox coords", ullon, ullat, lrlon, lrlat
		
	if force or not os.path.isfile(subset_filename):	
		ofStr 				= ' -of GTiff '
		bbStr 				= ' -te %s %s %s %s '%(ullon, lrlat, lrlon, ullat) 
		#bbStr				= ' '
		#resStr 			= ' -tr %s %s '%(pres, pres)
		resStr 				= ' -r mode '
		projectionStr 		= ' -t_srs EPSG:4326 '
		overwriteStr 		= ' -overwrite ' # Overwrite output if it exists
		additionalOptions 	= ' -co COMPRESS=DEFLATE -setci  ' # Additional options
		wh 					= ' -ts %d %d  ' % ( rasterXSize, rasterYSize )
		warpOptions 		= ofStr + bbStr + projectionStr + resStr + overwriteStr + additionalOptions + wh
		warpCMD 			= 'gdalwarp -q ' + warpOptions + browse_filename + ' ' + subset_filename
		execute(warpCMD)
	else:
		print subset_filename, "exists"
	
	# superimpose the suface water over map background
	#if force or not os.path.isfile(sw_osm_image):	
	if force or not os.path.isfile(sw_osm_image):	
		cmd = str.format("composite -quiet -gravity center -blend 60 {0} {1} {2}", subset_filename, osm_bg_image, sw_osm_image)
		execute(cmd)
		
if __name__ == '__main__':

	parser = argparse.ArgumentParser(description='Generate BrowseImage')
	apg_input = parser.add_argument_group('Input')
	apg_input.add_argument("scene", help="scene id")
	apg_input.add_argument("-f", "--force", action='store_true', help="forces new products to be generated")
	apg_input.add_argument("-v", "--verbose", action='store_true', help="Verbose on/off")

	options 		= parser.parse_args()
	
	scene 			= options.scene
	force			= options.force
	verbose			= options.verbose
 		  
	output_4326_hand	    = os.path.join(scene,"outputfile_4326_hand.tif")
	surface_water_image		= os.path.join(scene,"surface_water.png")
	surface_water_image_tif	= os.path.join(scene,"surface_water.tif")
	osm_bg_image			= os.path.join(scene,"osm_bg_image.png")
	sw_osm_image			= os.path.join(scene,"surface_water_osm.png")

	# Get Background Image 5% size
	indataset 		= gdal.Open( output_4326_hand )	
	geomatrix 		= indataset.GetGeoTransform()
	rasterXSize 	= indataset.RasterXSize
	rasterYSize 	= indataset.RasterYSize

	xorg			= geomatrix[0]
	yorg  			= geomatrix[3]

	xmax			= xorg + geomatrix[1]* rasterXSize
	ymax			= yorg - geomatrix[5]* rasterYSize

	centerlon		= (xorg + xmax) / 2
	centerlat		= (yorg + ymax) / 2
	rasterXSize		= int(rasterXSize * 0.05)
	rasterYSize		= int(rasterYSize * 0.05)

	if rasterXSize > 1280 or rasterYSize > 1280:
		rasterXSize /= 2
		rasterYSize	/= 2
		
	zoom			= 11	# This should probably be computed using ZoomForPixelSize

	mxorg, myorg 	= LatLonToMeters( yorg, xorg )
	mxmax, mymax	= LatLonToMeters( ymax, xmax )
		
	meters			= myorg - mymax
	meters			= mxmax - mxorg
	
	delta			= meters / rasterXSize
	zoom 			= ZoomForPixelSize( delta ) + 1	# just to be sure we fit
	
	if verbose:
		print "Computed Zoomlevel:", zoom
	
	#print "centerlon, centerlat", centerlon, centerlat
	ullon, ullat, lrlon, lrlat = bbox(centerlat, centerlon, zoom, rasterXSize, rasterYSize)
	#sys.exit(-1)
	
	#if force or not os.path.isfile(osm_bg_image):
	#mapquest_image(yorg, xorg, ymax, xmax, zoom, rasterXSize, rasterYSize, osm_bg_image)
	#google_center_image(centerlat, centerlon, zoom, rasterXSize, rasterYSize, osm_bg_image)
	#mapquest_center_image(centerlat, centerlon, zoom, rasterXSize, rasterYSize, osm_bg_image)

	if force or not os.path.isfile(osm_bg_image):
		mapbox_image(centerlat, centerlon, zoom, rasterXSize, rasterYSize, osm_bg_image)
   
	# surface water browse image
	#if force or not os.path.isfile(app.outputbrowse_image):	
	#cmd = "gdal_translate -q -of PNG -outsize 5% 5% " + output_4326_hand + " " + surface_water_image
	#if verbose:
	#	print(cmd)
	#os.system(cmd)

	if force or not os.path.isfile(surface_water_image):	
		cmd = str.format("gdal_translate -q -of PNG -projwin {0} {1} {2} {3} -outsize {4} {5} {6} {7}",
			ullon, ullat,lrlon,lrlat, rasterXSize, rasterYSize, output_4326_hand, surface_water_image)
		if verbose:
			print(cmd)
		os.system(cmd)
	
	# superimpose the suface water over map background
	if force or not os.path.isfile(sw_osm_image):	
		cmd = str.format("composite -quiet -gravity center {0} {1} {2}", surface_water_image, osm_bg_image, sw_osm_image)
		if verbose:
			print cmd
		os.system(cmd)
