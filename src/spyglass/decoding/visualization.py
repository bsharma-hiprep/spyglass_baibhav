import matplotlib.animation as animation
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from mpl_toolkits.axes_grid1.anchored_artists import AnchoredSizeBar
from ripple_detection import get_multiunit_population_firing_rate
from tqdm.auto import tqdm


def make_single_environment_movie(
    time_slice,
    classifier,
    results,
    position_info,
    marks,
    movie_name='video_name.mp4',
    sampling_frequency=500,
    video_slowdown=8,
    position_name=[
        'head_position_x', 'head_position_y'],
    direction_name='head_orientation',
    vmax=0.07,
):

    multiunit_spikes = (np.any(~np.isnan(marks.values), axis=1)
                        ).astype(float)
    multiunit_firing_rate = pd.DataFrame(
        get_multiunit_population_firing_rate(
            multiunit_spikes, sampling_frequency), index=position_info.index,
        columns=['firing_rate'])

    # Set up formatting for the movie files
    Writer = animation.writers['ffmpeg']
    fps = sampling_frequency // video_slowdown
    writer = Writer(fps=fps, bitrate=-1)

    # Set up data
    is_track_interior = classifier.environments[0].is_track_interior_
    posterior = (
        results
        .acausal_posterior
        .isel(time=time_slice)
        .sum("state")
        .where(is_track_interior))
    map_position_ind = posterior.argmax(["x_position", "y_position"])
    map_position = np.stack(
        (
            posterior.x_position[map_position_ind["x_position"]],
            posterior.y_position[map_position_ind["y_position"]],
        ),
        axis=1,
    )

    position = np.asarray(position_info.iloc[time_slice][position_name])
    direction = np.asarray(position_info.iloc[time_slice][direction_name])

    window_size = 501

    window_ind = np.arange(window_size) - window_size // 2
    rate = multiunit_firing_rate.iloc[
        slice(time_slice.start + window_ind[0],
              time_slice.stop + window_ind[-1])]

    with plt.style.context("dark_background"):
        # Set up plots
        fig, axes = plt.subplots(
            2,
            1,
            figsize=(6, 6),
            gridspec_kw={"height_ratios": [5, 1]},
            constrained_layout=False,
        )

        axes[0].tick_params(colors='white', which='both')
        axes[0].spines['bottom'].set_color('white')
        axes[0].spines['left'].set_color('white')

        position_dot = axes[0].scatter([], [], s=80, zorder=102, color='magenta',
                                       label='actual position', animated=True)
        (position_line,) = axes[0].plot(
            [], [], color='magenta', linewidth=5, animated=True)
        map_dot = axes[0].scatter([], [], s=80, zorder=102, color='green',
                                  label='decoded position', animated=True)
        (map_line,) = axes[0].plot([], [], 'green', linewidth=3, animated=True)

        mesh = (posterior
                .isel(time=0)
                .plot(
                    x='x_position',
                    y='y_position',
                    vmin=0.0,
                    vmax=vmax,
                    ax=axes[0],
                    animated=True,
                    add_colorbar=False
                ))
        axes[0].set_xlabel('')
        axes[0].set_ylabel('')
        axes[0].set_xlim(position_info[position_name[0]].min() - 10,
                         position_info[position_name[0]].max() + 10)
        axes[0].set_ylim(position_info[position_name[1]].min() - 10,
                         position_info[position_name[1]].max() + 10)
        axes[0].spines['top'].set_color('black')
        axes[0].spines['right'].set_color('black')
        title = axes[0].set_title(
            f'time = {posterior.isel(time=0).time.values:0.2f}',
        )
        fontprops = fm.FontProperties(size=16)
        scalebar = AnchoredSizeBar(axes[0].transData,
                                   20, '20 cm', 'lower right',
                                   pad=0.1,
                                   color='white',
                                   frameon=False,
                                   size_vertical=1,
                                   fontproperties=fontprops)

        axes[0].add_artist(scalebar)
        axes[0].axis('off')

        (multiunit_firing_line,) = axes[1].plot([], [], color='white', linewidth=2,
                                                animated=True, clip_on=False)
        axes[1].set_ylim((0.0, np.asarray(rate.max())))
        axes[1].set_xlim((window_ind[0] / sampling_frequency,
                          window_ind[-1] / sampling_frequency))
        axes[1].set_xlabel('Time [s]')
        axes[1].set_ylabel('Multiunit\n[spikes/s]')
        axes[1].set_facecolor("black")
        axes[1].spines['top'].set_color('black')
        axes[1].spines['right'].set_color('black')

        n_frames = posterior.shape[0]
        progress_bar = tqdm()
        progress_bar.reset(total=n_frames)

        def _update_plot(time_ind):
            start_ind = max(0, time_ind - 5)
            time_slice = slice(start_ind, time_ind)

            position_dot.set_offsets(position[time_ind])

            r = 4
            position_line.set_data(
                [position[time_ind, 0], position[time_ind, 0] +
                    r * np.cos(direction[time_ind])],
                [position[time_ind, 1], position[time_ind, 1] + r * np.sin(direction[time_ind])],)

            map_dot.set_offsets(map_position[time_ind])
            map_line.set_data(map_position[time_slice, 0],
                              map_position[time_slice, 1])

            mesh.set_array(
                posterior
                .isel(time=time_ind)
                .values
                .ravel(order="F")
            )

            title.set_text(
                f'time = {posterior.isel(time=time_ind).time.values:0.2f}')

            multiunit_firing_line.set_data(
                window_ind / sampling_frequency,
                np.asarray(rate.iloc[time_ind + (window_size // 2) + window_ind]))

            progress_bar.update()

            return (position_dot, position_line, map_dot, map_line, mesh, title, multiunit_firing_line)

        movie = animation.FuncAnimation(fig, _update_plot, frames=n_frames,
                                        interval=1000 / fps, blit=True)
        if movie_name is not None:
            movie.save(movie_name, writer=writer, dpi=200)

        return fig, movie


def setup_subplots(classifier, window_ind=None, rate=None, sampling_frequency=None):
    env_names = [env.environment_name for env in classifier.environments]

    mosaic = []
    for env_ind, env_name in enumerate(env_names):
        if len(mosaic) == 0:
            mosaic.append([])
            mosaic[-1].append(env_name)
        else:
            mosaic[-1].append(env_name)
        print('\n')

    mosaic.append(['multiunit'] * len(env_names))

    fig, axes = plt.subplot_mosaic(
        mosaic,
        figsize=(10, 6),
        gridspec_kw={"height_ratios": [5, 1]},
        constrained_layout=False
    )

    for env_name in env_names:
        ax = axes[env_name]
        env_ind = classifier.environments.index(env_name)
        ax.set_xlabel('')
        ax.set_ylabel('')
        ax.set_xlim(classifier.environments[env_ind].edges_[0].min() - 10,
                    classifier.environments[env_ind].edges_[0].max() + 10)
        ax.set_ylim(classifier.environments[env_ind].edges_[1].min() - 10,
                    classifier.environments[env_ind].edges_[1].max() + 10)
        ax.set_title(env_name)
        ax.axis('off')
        sns.despine(ax=axes[env_name])

    ax = axes['multiunit']
    ax.set_xlabel('Time [s]')
    ax.set_ylabel('Multiunit\n[spikes/s]')

    if rate is not None:
        ax.set_ylim((0.0, np.asarray(rate.max())))

    if window_ind is not None and sampling_frequency is not None:
        ax.set_xlim((window_ind[0] / sampling_frequency,
                     window_ind[-1] / sampling_frequency))
    sns.despine(ax=ax)

    return fig, axes


def make_multi_environment_movie(
    time_slice,
    classifier,
    results,
    position_info,
    marks,
    current_environment='',
    movie_name='video_name.mp4',
    sampling_frequency=500,
    video_slowdown=8,
    position_name=[
        'head_position_x', 'head_position_y'],
    direction_name='head_orientation',
    vmax=0.07,
):

    # Set up formatting for the movie files
    Writer = animation.writers['ffmpeg']
    fps = sampling_frequency // video_slowdown
    writer = Writer(fps=fps, bitrate=-1)

    # Set up neural data
    probability = results.isel(
        time=time_slice).acausal_posterior.sum('position')
    most_prob_env = probability.idxmax('state')
    env_names = [env.environment_name for env in classifier.environments]

    env_posteriors = {}
    for env_name in env_names:
        env = classifier.environments[classifier.environments.index(env_name)]
        n_position_bins = env.place_bin_centers_.shape[0]
        position_index = pd.MultiIndex.from_arrays(
            (env.place_bin_centers_[:, 0], env.place_bin_centers_[:, 1]),
            names=['x_position', 'y_position']
        )
        env_posteriors[env_name] = (
            results
            .sel(state=env_name, position=slice(0, n_position_bins))
            .isel(time=time_slice)
            .acausal_posterior
            .assign_coords(position=position_index)
            .unstack('position')
            .where(env.is_track_interior_))

    multiunit_spikes = (np.any(~np.isnan(marks.values), axis=1)
                        ).astype(float)
    multiunit_firing_rate = pd.DataFrame(
        get_multiunit_population_firing_rate(
            multiunit_spikes, sampling_frequency), index=position_info.index,
        columns=['firing_rate'])

    window_size = 501

    window_ind = np.arange(window_size) - window_size // 2
    rate = multiunit_firing_rate.iloc[
        slice(time_slice.start + window_ind[0],
              time_slice.stop + window_ind[-1])]

    # Set up behavioral data
    position = np.asarray(position_info.iloc[time_slice][position_name])
    direction = np.asarray(position_info.iloc[time_slice][direction_name])

    with plt.style.context("dark_background"):
        fig, axes = setup_subplots(
            classifier,
            window_ind=window_ind,
            rate=rate,
            sampling_frequency=sampling_frequency)

        position_dot = axes[current_environment].scatter(
            [], [], s=80, zorder=102, color='magenta',
            label='actual position', animated=True)
        (position_line,) = axes[current_environment].plot(
            [], [], color='magenta', linewidth=5, animated=True)

        meshes = {}
        titles = {}
        map_dots = {}
        for env_name, posterior in env_posteriors.items():
            meshes[env_name] = (
                posterior
                .isel(time=0)
                .plot(
                    x='x_position',
                    y='y_position',
                    vmin=0.0,
                    vmax=vmax,
                    ax=axes[env_name],
                    animated=True,
                    add_colorbar=False
                ))
            prob = float(probability.isel(time=0).sel(state=env_name))
            titles[env_name] = axes[env_name].set_title(
                f"environment = {env_name}\nprob. = {prob:0.2f}")
            map_dots[env_name] = axes[env_name].scatter(
                [], [], s=80, zorder=102, color='green',
                animated=True)

        (multiunit_firing_line,) = axes['multiunit'].plot(
            [], [], color='white', linewidth=2,
            animated=True, clip_on=False)

        n_frames = posterior.shape[0]
        progress_bar = tqdm()
        progress_bar.reset(total=n_frames)

        def _update_plot(time_ind):
            position_dot.set_offsets(position[time_ind])

            r = 4
            position_line.set_data(
                [position[time_ind, 0], position[time_ind, 0] +
                    r * np.cos(direction[time_ind])],
                [position[time_ind, 1], position[time_ind, 1] + r * np.sin(direction[time_ind])],)

            for env_name, mesh in meshes.items():
                posterior = env_posteriors[env_name].isel(
                    time=time_ind).values.ravel(order="F")
                mesh.set_array(posterior)
                prob = float(probability.isel(
                    time=time_ind).sel(state=env_name))
                titles[env_name].set_text(
                    f"environment = {env_name}\nprob. = {prob:0.2f}")
                if env_name == most_prob_env.isel(time=time_ind):
                    env = classifier.environments[classifier.environments.index(
                        env_name)]
                    map_dots[env_name].set_offsets(
                        env.place_bin_centers_[np.nanargmax(posterior)])
                    map_dots[env_name].set_alpha(1.0)
                else:
                    map_dots[env_name].set_alpha(0.0)

            multiunit_firing_line.set_data(
                window_ind / sampling_frequency,
                np.asarray(rate.iloc[time_ind + (window_size // 2) + window_ind]))

            progress_bar.update()

            return (position_dot, position_line, *meshes.values(), *map_dots.values(), multiunit_firing_line)

        movie = animation.FuncAnimation(fig, _update_plot, frames=n_frames,
                                        interval=1000 / fps, blit=True)
        if movie_name is not None:
            movie.save(movie_name, writer=writer, dpi=200)

        return fig, movie