"""Matplotlib layout, controls, and rendering for the Game of Life."""

import matplotlib.animation as animation
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle
from matplotlib.widgets import Button, CheckButtons, RadioButtons, Slider


class GameOfLifeUI:
    """Display a simulation controller and forward user actions to it."""

    def __init__(self, simulation):
        self.simulation = simulation
        self.fade_grid = np.zeros_like(simulation.grid)
        self.is_dragging = False
        self.tail_fade_rate = 0.33
        self.color = np.array([46, 204, 113]) / 255.0
        self.tail_color = np.array([171, 235, 198]) / 255.0
        self.h_line = None
        self.v_line = None

        self.fig, self.ax = plt.subplots()
        self.ax.axis('off')
        self.ax.set_title("Conway's Game of Life", fontsize=24, color='mediumseagreen',
                          fontweight='heavy', style='italic', family='fantasy', pad=20)
        self.fig.patch.set_facecolor(np.array([34, 47, 62]) / 255.0)
        self.img = self.ax.imshow(simulation.grid, interpolation='nearest')
        self.perc_text = self.ax.text(
            0.5, 0.95, '', transform=self.ax.transAxes, fontsize=22, color='white',
            ha='center', va='center', family='Comic Sans MS')
        self.ax.add_patch(Rectangle(
            (-0.5, -0.5), simulation.size, simulation.size, linewidth=2,
            edgecolor='grey', facecolor='none', alpha=0.9))

        self._create_controls()
        self.fig.canvas.mpl_connect('button_press_event', self.on_click)
        self.fig.canvas.mpl_connect('motion_notify_event', self.on_motion)
        self.fig.canvas.mpl_connect('button_release_event', self.on_release)
        self.fig.canvas.mpl_connect('key_press_event', self.on_key_press)
        self.ani = animation.FuncAnimation(self.fig, self.update, interval=25, save_count=50)

    def _create_controls(self):
        axcolor = 'lightgoldenrodyellow'
        ax_fade_rate = self.fig.add_axes([0.25, 0.01, 0.65, 0.03], facecolor=axcolor)
        self.s_fade_rate = Slider(ax_fade_rate, 'Fade Rate', 0.0, 1.0, valinit=self.tail_fade_rate)
        self.s_fade_rate.on_changed(self.update_fade_rate)

        self.cell_color_sliders = self._create_color_sliders(self.color, 0.60, 0.845, 'Cell Color')
        self.tail_color_sliders = self._create_color_sliders(self.tail_color, 0.28, 0.53, 'Tail Effect Color')
        for slider in self.cell_color_sliders:
            slider.on_changed(self.update_cell_color)
        for slider in self.tail_color_sliders:
            slider.on_changed(self.update_tail_color)

        ax_checkbox = self.fig.add_axes([0.03, 0.80, 0.17, 0.05])
        self.check = CheckButtons(ax_checkbox, ['Show Grid'], [False])
        self.check.on_clicked(self.toggle_middle_lines)

        boundary_options = [
            ('Wrap (toroidal)', 'wrap'),
            ('Open (absorbing)', 'open'),
            ('Fill edges (zeros)', 'fill'),
        ]
        self.boundary_label_to_mode = dict(boundary_options)
        ax_boundary = self.fig.add_axes([0.03, 0.68, 0.17, 0.10], facecolor=axcolor)
        active = [mode for _, mode in boundary_options].index(self.simulation.boundary_mode)
        self.boundary_radio = RadioButtons(ax_boundary, [name for name, _ in boundary_options], active=active)
        for label in self.boundary_radio.labels:
            label.set_fontsize(9)
        self.boundary_radio.on_clicked(self.set_boundary_mode)

        ax_ratio = self.fig.add_axes([0.25, 0.04, 0.65, 0.03], facecolor=axcolor)
        self.s_ratio = Slider(ax_ratio, 'Seeding Ratio', 0.0, 1.0,
                              valinit=self.simulation.seeding_ratio)
        self.s_ratio.on_changed(self.update_seeding_ratio)

        ax_reset = self.fig.add_axes([0.82, 0.08, 0.1, 0.04])
        self.b_reset = Button(ax_reset, 'Reset', color=axcolor, hovercolor='0.975')
        self.b_reset.on_clicked(self.reset)
        ax_clear = self.fig.add_axes([0.82, 0.14, 0.1, 0.04])
        self.b_clear = Button(ax_clear, 'Clear', color=axcolor, hovercolor='0.975')
        self.b_clear.on_clicked(self.clear_grid)

    def _create_color_sliders(self, color, bottom, title_y, title):
        top_right_x = 0.95
        slider_width = 0.02
        slider_height = 0.2
        spacing = 0.01
        sliders = []
        for index, label in enumerate(('R', 'G', 'B')):
            axis = self.fig.add_axes(
                [top_right_x - (3 - index) * (slider_width + spacing),
                 bottom, slider_width, slider_height], facecolor='lightgoldenrodyellow')
            slider = Slider(axis, label, 0.0, 1.0, valinit=color[index], orientation='vertical')
            slider.valtext.set_visible(False)
            sliders.append(slider)
        self.fig.text(top_right_x - 1.5 * (slider_width + spacing), title_y, title,
                      va='bottom', ha='center', color='black', fontsize=10)
        return sliders

    def toggle_middle_lines(self, label):
        if label != 'Show Grid':
            return
        if self.check.get_status()[0]:
            mid = self.simulation.size // 2
            if self.h_line is None:
                self.h_line = self.ax.axhline(y=mid, color='cyan', linestyle='--', alpha=0.3, linewidth=1)
            if self.v_line is None:
                self.v_line = self.ax.axvline(x=mid, color='cyan', linestyle='--', alpha=0.3, linewidth=1)
        else:
            if self.h_line is not None:
                self.h_line.remove()
                self.h_line = None
            if self.v_line is not None:
                self.v_line.remove()
                self.v_line = None
        self.update_plot()

    def set_boundary_mode(self, label):
        self.simulation.set_boundary_mode(self.boundary_label_to_mode[label])

    def update_fade_rate(self, val):
        self.tail_fade_rate = val
        self.update_plot()

    def _update_alpha(self):
        grid = self.simulation.grid
        self.fade_grid[grid == 1] = 1
        self.fade_grid[grid == 0] -= self.tail_fade_rate
        self.fade_grid[self.fade_grid < 0] = 0

    def _rgba(self):
        grid = self.simulation.grid
        rgba_array = np.zeros((*grid.shape, 4))
        rgba_array[grid == 1, :3] = self.color
        rgba_array[grid == 0, :3] = self.tail_color
        rgba_array[..., 3] = self.fade_grid
        return rgba_array

    def _get_grid_coord(self, x, y):
        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()
        size = self.simulation.size
        x_grid = int(size * (x - xlim[0]) / (xlim[1] - xlim[0]))
        y_grid = size - 1 - int(size * (y - ylim[0]) / (ylim[1] - ylim[0]))
        return x_grid, y_grid

    def on_click(self, event):
        if event.inaxes == self.ax and event.button == 1:
            self.is_dragging = True
            self.seed_grid(event)

    def on_motion(self, event):
        if self.is_dragging and event.inaxes == self.ax:
            self.seed_grid(event)

    def on_release(self, event):
        if event.button == 1:
            self.is_dragging = False

    def on_key_press(self, event):
        if event.key == ' ':
            if self.simulation.toggle_running():
                self.ani.event_source.start()
            else:
                self.ani.event_source.stop()

    def seed_grid(self, event):
        x, y = self._get_grid_coord(event.xdata, event.ydata)
        if self.simulation.seed_cell(x, y):
            self.fade_grid[y, x] = 1
            self.update_plot()

    def update_plot(self):
        self.img.set_data(self._rgba())
        self.fig.canvas.draw_idle()

    def update(self, *args):
        if not self.simulation.is_running:
            return self.img,
        self.simulation.step()
        self._update_alpha()
        self.img.set_data(self._rgba())
        percentage = np.mean(self.simulation.grid == 1) * 100
        self.perc_text.set_text(f'Living Cells: {percentage:.2f}%')
        return self.img, self.perc_text

    def _reset_trails(self):
        self.fade_grid = np.zeros_like(self.simulation.grid)
        self.update_plot()

    def update_seeding_ratio(self, val):
        self.simulation.reset(seeding_ratio=val)
        self._reset_trails()

    def reset(self, event):
        self.simulation.reset()
        self._reset_trails()

    def clear_grid(self, event):
        self.simulation.clear()
        self._reset_trails()

    def update_cell_color(self, val):
        self.color[:] = [slider.val for slider in self.cell_color_sliders]
        self.update_plot()

    def update_tail_color(self, val):
        self.tail_color[:] = [slider.val for slider in self.tail_color_sliders]
        self.update_plot()

    def show(self):
        """Open the interactive window."""
        plt.show()
