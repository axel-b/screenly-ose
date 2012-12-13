/*
Copyright (c) 2012, Broadcom Europe Ltd
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
    * Redistributions of source code must retain the above copyright
      notice, this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright
      notice, this list of conditions and the following disclaimer in the
      documentation and/or other materials provided with the distribution.
    * Neither the name of the copyright holder nor the
      names of its contributors may be used to endorse or promote products
      derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY
DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
*/

// A simple demo using dispmanx to display an overlay
// hacked to implement a fader/shutter overlay

// NOTE: it interacts on stdin/stdout, via a 'fixed protocol'
// and thus:
// all warnings, messages, diagnostics that do _not_ belong to the interaction,
// must be written to stderr

#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <assert.h>
#include <unistd.h>
#include <sys/time.h>

#include "bcm_host.h"

//#define WIDTH   200
//#define HEIGHT  200

#define ALIGN_UP(x,y)  ((x + (y)-1) & ~((y)-1))

typedef struct
{
    DISPMANX_DISPLAY_HANDLE_T   display;
    DISPMANX_MODEINFO_T         info;
    void                       *image;
    DISPMANX_UPDATE_HANDLE_T    update;
    DISPMANX_RESOURCE_HANDLE_T  resource;
    DISPMANX_ELEMENT_HANDLE_T   element;
    uint32_t                    vc_image_ptr;
    int				connected;

} RECT_VARS_T;

static RECT_VARS_T  gRectVars;
static VC_RECT_T       src_rect;
static VC_RECT_T       dst_rect;
static VC_IMAGE_TYPE_T type = VC_IMAGE_RGB565;

static char* program = "shutter";

unsigned long RGB888_to_RGB565(unsigned long rgb)
{
	return (((rgb >> 19) & 0x1f) << 11) |
               (((rgb >> 10) & 0x3f) <<  5) |
               (((rgb >>  3) & 0x1f)      );
}

static void FillRect( VC_IMAGE_TYPE_T type, void *image, int pitch, int aligned_height, int x, int y, int w, int h, int val )
{
    int         row;
    int         col;

    uint16_t *line = (uint16_t *)image + y * (pitch>>1) + x;

    for ( row = 0; row < h; row++ )
    {
        for ( col = 0; col < w; col++ )
        {
            line[col] = val;
        }
        line += (pitch>>1);
    }
}

static VC_DISPMANX_ALPHA_T alpha = { DISPMANX_FLAGS_ALPHA_FROM_SOURCE | DISPMANX_FLAGS_ALPHA_FIXED_ALL_PIXELS, 
                             0, /*alpha 0->255*/
                             0 };

//float totalTime = .4; //sec
//
//float delay = totalTime/2;
////float stepDelay = .05 / 128; // ((totalTime-delay)/2)/256;
//float stepDelay = ((totalTime-delay)/2)/51;
////float stepDelay = .05 / 256; // ((totalTime-delay)/2)/256;

//halfTime has to be expressed as nanoseconds
long halfTimeNano = 400*1000*1000; // 400 ms

void hard_out(RECT_VARS_T *vars, int color);
void hard_in(RECT_VARS_T *vars);
void fade_out(RECT_VARS_T *vars, int color);
void fade_in(RECT_VARS_T *vars);
void disconnect(RECT_VARS_T *vars);

static struct timespec stepDelay;

int main(int argc, char**argv)
{
    RECT_VARS_T    *vars;

    

    vars = &gRectVars;
    vars->connected = 0;

    stepDelay.tv_sec = 0;
    stepDelay.tv_nsec = halfTimeNano / 51;

    bcm_host_init();



//forever:
//  read line
//  parse command
//     case  fade-to-black:
//	     open-display
//           create frame(black)
//           decrease transparency (opacity) till we have solid color
//           write ack
//     case  fade-to-white:
//	     open-display
//           create frame(white)
//           decrease transparency (opacity) till we have solid color
//           write ack
//     case  fade-in:
//           increase transparency (opacity) till we have full transparency
//           delete frame
//           close display
//           write ack





    int nbuf = 100;
    char *buf = (char*)malloc(sizeof(char)*nbuf);
   

    for(;;) {
        char *s = fgets(buf, nbuf, stdin);
	if (s == NULL && feof(stdin))
		break;

	if (strncmp(s, "fade-in", strlen("fade-in")) == 0) {
		fade_in(vars);
		fprintf(stdout, "done\n");
		fflush(stdout);
	} else if (strncmp(s, "fade-to-white", strlen("fade-to-white")) == 0) {
		int color = 0xFFFF; //white
		fade_out(vars, color);
		fprintf(stdout, "done\n");
		fflush(stdout);
	} else if (strncmp(s, "fade-to-black", strlen("fade-to-black")) == 0) {
		int color = 0x0000; // black
		fade_out(vars, color);
		fprintf(stdout, "done\n");
		fflush(stdout);
	} else if (strncmp(s, "fade-to-color", strlen("fade-to-color")) == 0) {
		int color = strtol(s+strlen("fade-to-color")+1, 0, 0);
		color = RGB888_to_RGB565(color);
		fade_out(vars, color);
		fprintf(stdout, "done\n");
		fflush(stdout);
	} else if (strncmp(s, "hard-in", strlen("hard-in")) == 0) {
		hard_in(vars);
		fprintf(stdout, "done\n");
		fflush(stdout);
	} else if (strncmp(s, "hard-to-white", strlen("hard-to-white")) == 0) {
		int color = 0xFFFF; //white
		hard_out(vars, color);
		fprintf(stdout, "done\n");
		fflush(stdout);
	} else if (strncmp(s, "hard-to-black", strlen("hard-to-black")) == 0) {
		int color = 0x0000; // black
		hard_out(vars, color);
		fprintf(stdout, "done\n");
		fflush(stdout);
	} else if (strncmp(s, "hard-to-color", strlen("hard-to-color")) == 0) {
		int color = strtol(s+strlen("hard-to-color")+1, 0, 0);
		color = RGB888_to_RGB565(color);
		hard_out(vars, color);
		fprintf(stdout, "done\n");
		fflush(stdout);
	}
    }

    if(vars->connected)
        disconnect(vars);
    return 0;
}

// return 1 if everthing went ok
// return 0 otherwise
// if we return 0, there are no resources that must be freed later
int create_overlay(RECT_VARS_T *vars, int color)
{
    uint32_t        screen = 0;
    int             ret;

    if (vars->connected) {
	fprintf(stderr, "%s: already connected, not creating overlay again\n", program);
	return 0;
    }
    //fprintf(stderr, "%s:Open display[%i]...\n", program, screen );
    vars->display = vc_dispmanx_display_open( screen );
    if (vars->display == 0) {
        fprintf(stderr,  "%s: no display\n", program);
        return 0;
    }


    ret = vc_dispmanx_display_get_info( vars->display, &vars->info);
    if(ret != 0) {
        fprintf(stderr, "%s: cannot get display info\n", program);
        return 0; 
    }
    //fprintf(stderr, "%s: Display is %d x %d\n", program, vars->info.width, vars->info.height );


    int width = vars->info.width, height = vars->info.height;
    int pitch = ALIGN_UP(width*2, 32);
    int aligned_height = ALIGN_UP(height, 16);
    
    //fprintf(stderr, "%s: Display pitch %d height %d\n", program, pitch, height );

    vars->image = calloc( 1, pitch * height );
    if (vars->image == 0) {
        fprintf(stderr, "%s: cannot allocate overlay image\n", program);
        return 0;
    }

    FillRect( type, vars->image, pitch, aligned_height,  0,  0, width,      height,      color);
    //FillRect( type, vars->image, pitch, aligned_height,  0,  0, width,      height,      0x0000 );
    //FillRect( type, vars->image, pitch, aligned_height,  0,  0, width,      height,      0xFFFF );
    //FillRect( type, vars->image, pitch, aligned_height,  0,  0, width,      height,      0xF800 );
    //FillRect( type, vars->image, pitch, aligned_height, 20, 20, width - 40, height - 40, 0x07E0 );
    //FillRect( type, vars->image, pitch, aligned_height, 40, 40, width - 80, height - 80, 0x001F );

    vars->resource = vc_dispmanx_resource_create( type,
                                                  width,
                                                  height,
                                                  &vars->vc_image_ptr );
    if (vars->resource == 0) {
        fprintf(stderr, "%s: cannot create overlay resource\n", program);
        free(vars->image);
        return 0;
    }
    vc_dispmanx_rect_set( &dst_rect, 0, 0, width, height);
    ret = vc_dispmanx_resource_write_data(  vars->resource,
                                            type,
                                            pitch,
                                            vars->image,
                                            &dst_rect );
    if( ret != 0 ) {
        fprintf(stderr, "%s: cannot write overlay resource\n", program);
        free(vars->image);
        return 0;
    }
    vars->update = vc_dispmanx_update_start( 10 );
    if( !vars->update ) {
        fprintf(stderr, "%s: cannot start overlay update\n", program);
        free(vars->image);
        return 0;
    }

    vc_dispmanx_rect_set( &src_rect, 0, 0, width << 16, height << 16 );

    vc_dispmanx_rect_set( &dst_rect, ( vars->info.width - width ) / 2,
                                     ( vars->info.height - height ) / 2,
                                     width,
                                     height );

    vars->element = vc_dispmanx_element_add(    vars->update,
                                                vars->display,
                                                2500,               // layer
                                                &dst_rect,
                                                vars->resource,
                                                &src_rect,
                                                DISPMANX_PROTECTION_NONE,
                                                &alpha,
                                                NULL,             // clamp
                                                VC_IMAGE_ROT0 );

    ret = vc_dispmanx_update_submit_sync( vars->update );
    if( ret != 0 ) {
        fprintf(stderr, "%s: cannot sync overlay update\n", program);
        free(vars->image);
        return 0;
    }

    return 1; // everything went fine
}


void fade(RECT_VARS_T *vars, int min, int max, int step, struct timespec* delay)
{
    int             ret;

    while(alpha.opacity + step <= max && alpha.opacity + step >= min) {

        //fprintf(stderr, "%s: %d %d Sleeping for 1 seconds...\n", program, i, alpha.opacity );
    	nanosleep( delay, 0);
    	alpha.opacity += step;
	
        vars->update = vc_dispmanx_update_start( 10 );
        if( ! vars->update ) {
            fprintf(stderr, "%s: cannot start fade update\n", program);
            return;
        }
    	vc_dispmanx_element_change_attributes( vars->update,
					   vars->element,
					   (1<<1),
					   2500,
                                           alpha.opacity,
                                                &dst_rect,
                                                &src_rect,
                                                vars->resource,
                                                VC_IMAGE_ROT0 );
    	ret = vc_dispmanx_update_submit_sync( vars->update );
    	if( ret != 0 ) {
            fprintf(stderr, "%s: cannot sync fade update\n", program);
            return;
        }
    }
}

void hard_out(RECT_VARS_T *vars, int color)
{
    if (vars->connected) {
	fprintf(stderr, "%s: already connected, not hard cut out again\n", program);
	return;
    }
    alpha.opacity = 255;
    if (!create_overlay(vars, color)) {
        fprintf(stderr, "%s: cannot create overlay for hard-out\n", program);
        return;
    }
    vars->connected  = 1;
}

void fade_out(RECT_VARS_T *vars, int color)
{
    if (vars->connected) {
	fprintf(stderr, "%s: already connected, not fading out again\n", program);
	return;
    }
    alpha.opacity = 0;
    if (!create_overlay(vars, color)) {
        fprintf(stderr, "%s: cannot create overlay for fade-out\n", program);
        return;
    }
    vars->connected  = 1;
    fade(vars, 0, 255, +5, &stepDelay);
}

void hard_in(RECT_VARS_T *vars)
{
    if (!vars->connected) {
	fprintf(stderr, "%s: not connected, not hard cut in\n", program);
	return;
    }
    disconnect(vars);
}

void fade_in(RECT_VARS_T *vars)
{
    if (!vars->connected) {
	fprintf(stderr, "%s: not connected, not fading in\n", program);
	return;
    }
    fade(vars, 0, 255, -5, &stepDelay);
    disconnect(vars);
}

void disconnect(RECT_VARS_T *vars)
{
    int             ret;

    if (!vars->connected) {
	fprintf(stderr, "%s: not connected, not disconnecting\n", program);
	return;
    }
    vars->update = vc_dispmanx_update_start( 10 );
    if( !vars->update ) {
        fprintf(stderr, "%s: cannot start disconnect update\n", program);
        return;
    }
    ret = vc_dispmanx_element_remove( vars->update, vars->element );
    if( ret != 0 ){
        fprintf(stderr, "%s: disconnect: cannot remove element\n", program);
        return;
    }
    ret = vc_dispmanx_update_submit_sync( vars->update );
    if( ret != 0 ) {
        fprintf(stderr, "%s: cannot sync disconnect update\n", program);
        return;
    }
    ret = vc_dispmanx_resource_delete( vars->resource );
    if( ret != 0 ) {
        fprintf(stderr, "%s: disconnect: cannot delete resource\n", program);
        return;
    }
    ret = vc_dispmanx_display_close( vars->display );
    if( ret != 0 ) {
        fprintf(stderr, "%s: disconnect: cannot close display\n", program);
        return;
    }

    free(vars->image);
    vars->image = 0;

    vars->connected = 0;
}

