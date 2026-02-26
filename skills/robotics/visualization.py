# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Visualization skill for trajectory and training data plots."""
import os
import logging

logger = logging.getLogger("skill.visualization")
BASE_DIR = os.path.expanduser("~/agent-stack")

# Dark theme colors matching the dashboard
DARK_BG = "#1a1a2e"
DARK_PANEL = "#16213e"
AMBER = "#f0a500"
TEAL = "#00d2d3"
LIGHT_TEXT = "#e0e0e0"
GRID_COLOR = "#2a2a4a"
ERROR_RED = "#ff6b6b"
SUCCESS_GREEN = "#6bff6b"


class VisualizationSkill:
    """Generates publication-quality plots with dark theme styling."""

    def _apply_dark_theme(self, fig, ax):
        """Apply consistent dark theme to a matplotlib figure and axes."""
        fig.patch.set_facecolor(DARK_BG)
        if isinstance(ax, (list,)):
            for a in ax:
                self._style_axis(a)
        else:
            self._style_axis(ax)

    def _style_axis(self, ax):
        """Style a single axis with dark theme."""
        ax.set_facecolor(DARK_PANEL)
        ax.tick_params(colors=LIGHT_TEXT, which="both")
        ax.xaxis.label.set_color(LIGHT_TEXT)
        ax.yaxis.label.set_color(LIGHT_TEXT)
        ax.title.set_color(LIGHT_TEXT)
        for spine in ax.spines.values():
            spine.set_color(GRID_COLOR)
        ax.grid(True, color=GRID_COLOR, alpha=0.3, linestyle="--")

    def plot_comparison(self, traj_a: list, traj_b: list, metrics: dict = None,
                        save_path: str = None) -> str:
        """Plot side-by-side trajectory comparison.

        traj_a, traj_b: lists of [x, y, z] or joint positions per timestep.
        metrics: dict of comparison metrics to display.
        save_path: file path to save the plot.
        """
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        save_path = save_path or os.path.join(BASE_DIR, "plots", "trajectory_comparison.png")
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        traj_a_np = np.array(traj_a)
        traj_b_np = np.array(traj_b)
        n_dims = traj_a_np.shape[1] if traj_a_np.ndim > 1 else 1

        fig, axes = plt.subplots(n_dims, 1, figsize=(12, 3 * n_dims), squeeze=False)
        self._apply_dark_theme(fig, [ax for row in axes for ax in row])

        for j in range(n_dims):
            ax = axes[j, 0]
            data_a = traj_a_np[:, j] if traj_a_np.ndim > 1 else traj_a_np
            data_b = traj_b_np[:, j] if traj_b_np.ndim > 1 else traj_b_np

            t_a = np.arange(len(data_a))
            t_b = np.arange(len(data_b))

            ax.plot(t_a, data_a, color=AMBER, linewidth=1.5, label="Trajectory A", alpha=0.9)
            ax.plot(t_b, data_b, color=TEAL, linewidth=1.5, label="Trajectory B", alpha=0.9)

            ax.set_ylabel(f"Joint {j}" if n_dims > 1 else "Value", fontsize=10)
            ax.legend(facecolor=DARK_PANEL, edgecolor=GRID_COLOR, labelcolor=LIGHT_TEXT,
                      fontsize=8)

        axes[-1, 0].set_xlabel("Timestep", fontsize=10)
        fig.suptitle("Trajectory Comparison", color=LIGHT_TEXT, fontsize=14, fontweight="bold")

        # Add metrics text box if provided
        if metrics:
            text_lines = [f"{k}: {v:.4f}" if isinstance(v, float) else f"{k}: {v}"
                          for k, v in metrics.items()]
            text_str = "\n".join(text_lines)
            fig.text(0.98, 0.02, text_str, fontsize=8, color=LIGHT_TEXT,
                     ha="right", va="bottom", fontfamily="monospace",
                     bbox=dict(boxstyle="round", facecolor=DARK_PANEL, edgecolor=GRID_COLOR,
                               alpha=0.8))

        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        fig.savefig(save_path, dpi=150, facecolor=DARK_BG, bbox_inches="tight")
        plt.close(fig)

        logger.info(f"Saved comparison plot to {save_path}")
        return save_path

    def plot_manipulability(self, trajectory: list, save_path: str = None) -> str:
        """Plot manipulability index along trajectory.

        trajectory: list of dicts with "manipulability", "translational", "rotational" keys.
        """
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        save_path = save_path or os.path.join(BASE_DIR, "plots", "manipulability.png")
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        manip = [p.get("manipulability", 0.0) for p in trajectory]
        trans = [p.get("translational", 0.0) for p in trajectory]
        rot = [p.get("rotational", 0.0) for p in trajectory]
        t = np.arange(len(manip))

        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
        self._apply_dark_theme(fig, [ax1, ax2, ax3])

        # Total manipulability
        ax1.plot(t, manip, color=AMBER, linewidth=2, label="Total")
        ax1.fill_between(t, 0, manip, color=AMBER, alpha=0.15)
        ax1.set_ylabel("Manipulability", fontsize=10)
        ax1.set_title("Yoshikawa Manipulability Index", fontsize=12, fontweight="bold")
        ax1.axhline(y=0.01, color=ERROR_RED, linestyle="--", alpha=0.7, label="Singularity threshold")
        ax1.legend(facecolor=DARK_PANEL, edgecolor=GRID_COLOR, labelcolor=LIGHT_TEXT)

        # Translational
        ax2.plot(t, trans, color=TEAL, linewidth=2, label="Translational")
        ax2.fill_between(t, 0, trans, color=TEAL, alpha=0.15)
        ax2.set_ylabel("Translational", fontsize=10)
        ax2.legend(facecolor=DARK_PANEL, edgecolor=GRID_COLOR, labelcolor=LIGHT_TEXT)

        # Rotational
        ax3.plot(t, rot, color="#e056a0", linewidth=2, label="Rotational")
        ax3.fill_between(t, 0, rot, color="#e056a0", alpha=0.15)
        ax3.set_ylabel("Rotational", fontsize=10)
        ax3.set_xlabel("Waypoint Index", fontsize=10)
        ax3.legend(facecolor=DARK_PANEL, edgecolor=GRID_COLOR, labelcolor=LIGHT_TEXT)

        plt.tight_layout()
        fig.savefig(save_path, dpi=150, facecolor=DARK_BG, bbox_inches="tight")
        plt.close(fig)

        logger.info(f"Saved manipulability plot to {save_path}")
        return save_path

    def plot_training_curves(self, training_run: dict, save_path: str = None) -> str:
        """Plot loss curves from training data.

        training_run: dict with keys like "epochs", "train_loss", "val_loss",
                      "learning_rate", optionally "metrics" (dict of named metric lists).
        """
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        save_path = save_path or os.path.join(BASE_DIR, "plots", "training_curves.png")
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        epochs = training_run.get("epochs", list(range(len(training_run.get("train_loss", [])))))
        train_loss = training_run.get("train_loss", [])
        val_loss = training_run.get("val_loss", [])
        lr = training_run.get("learning_rate", [])
        extra_metrics = training_run.get("metrics", {})

        n_panels = 1 + (1 if lr else 0) + len(extra_metrics)
        fig, axes = plt.subplots(n_panels, 1, figsize=(12, 3.5 * n_panels), sharex=True)
        if n_panels == 1:
            axes = [axes]
        self._apply_dark_theme(fig, axes)

        # Loss plot
        ax = axes[0]
        if train_loss:
            ax.plot(epochs[:len(train_loss)], train_loss, color=AMBER, linewidth=2,
                    label="Train Loss")
        if val_loss:
            ax.plot(epochs[:len(val_loss)], val_loss, color=TEAL, linewidth=2,
                    label="Val Loss", linestyle="--")
        ax.set_ylabel("Loss", fontsize=10)
        ax.set_title("Training Curves", fontsize=12, fontweight="bold")
        ax.set_yscale("log")
        ax.legend(facecolor=DARK_PANEL, edgecolor=GRID_COLOR, labelcolor=LIGHT_TEXT)

        panel_idx = 1

        # Learning rate plot
        if lr:
            ax = axes[panel_idx]
            ax.plot(epochs[:len(lr)], lr, color="#e056a0", linewidth=2, label="Learning Rate")
            ax.set_ylabel("LR", fontsize=10)
            ax.set_yscale("log")
            ax.legend(facecolor=DARK_PANEL, edgecolor=GRID_COLOR, labelcolor=LIGHT_TEXT)
            panel_idx += 1

        # Extra metrics
        extra_colors = ["#6bff6b", "#ff6b6b", "#6b6bff", "#ffff6b"]
        for i, (name, values) in enumerate(extra_metrics.items()):
            ax = axes[panel_idx]
            color = extra_colors[i % len(extra_colors)]
            ax.plot(epochs[:len(values)], values, color=color, linewidth=2, label=name)
            ax.set_ylabel(name, fontsize=10)
            ax.legend(facecolor=DARK_PANEL, edgecolor=GRID_COLOR, labelcolor=LIGHT_TEXT)
            panel_idx += 1

        axes[-1].set_xlabel("Epoch", fontsize=10)
        plt.tight_layout()
        fig.savefig(save_path, dpi=150, facecolor=DARK_BG, bbox_inches="tight")
        plt.close(fig)

        logger.info(f"Saved training curves to {save_path}")
        return save_path

    def save_publication_plot(self, data: dict, title: str,
                              save_path: str = None) -> str:
        """Generate publication-quality plot with proper formatting.

        data: {"x": [...], "series": [{"label": str, "y": [...], "color": str (optional)}]}
              or {"x": [...], "y": [...], "label": str}
        """
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        save_path = save_path or os.path.join(BASE_DIR, "plots", "publication.png")
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        fig, ax = plt.subplots(figsize=(8, 5))
        self._apply_dark_theme(fig, ax)

        x = np.array(data.get("x", []))
        default_colors = [AMBER, TEAL, "#e056a0", SUCCESS_GREEN, ERROR_RED, "#6b6bff"]

        if "series" in data:
            for i, series in enumerate(data["series"]):
                y = np.array(series["y"])
                label = series.get("label", f"Series {i}")
                color = series.get("color", default_colors[i % len(default_colors)])
                style = series.get("style", "-")
                ax.plot(x[:len(y)], y, color=color, linewidth=2, label=label, linestyle=style)
        elif "y" in data:
            y = np.array(data["y"])
            label = data.get("label", "Data")
            ax.plot(x[:len(y)], y, color=AMBER, linewidth=2, label=label)

        ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel(data.get("xlabel", "X"), fontsize=11)
        ax.set_ylabel(data.get("ylabel", "Y"), fontsize=11)

        legend = ax.legend(facecolor=DARK_PANEL, edgecolor=GRID_COLOR,
                           labelcolor=LIGHT_TEXT, fontsize=9,
                           loc=data.get("legend_loc", "best"))
        legend.get_frame().set_alpha(0.9)

        # Publication formatting
        ax.tick_params(labelsize=9)
        for spine in ax.spines.values():
            spine.set_linewidth(0.5)

        plt.tight_layout()
        fig.savefig(save_path, dpi=300, facecolor=DARK_BG, bbox_inches="tight")
        plt.close(fig)

        logger.info(f"Saved publication plot to {save_path}")
        return save_path
