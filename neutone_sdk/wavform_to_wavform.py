import logging
from abc import abstractmethod
from typing import NamedTuple, Dict, List, Optional, Final
from neutone_sdk.parameter import NeutoneParameter

import torch as tr
from torch import Tensor, nn

from neutone_sdk import NeutoneModel
from neutone_sdk.utils import validate_waveform

logging.basicConfig()
log = logging.getLogger(__name__)


class WaveformToWaveformMetadata(NamedTuple):
    model_name: str
    model_authors: List[str]
    model_version: str
    model_short_description: str
    model_long_description: str
    technical_description: str
    technical_links: Dict[str, str]
    tags: List[str]
    citation: str
    is_experimental: bool
    neutone_parameters: Dict[str, Dict[str, str]]
    wet_default_value: float
    dry_default_value: float
    output_gain_default_value: float
    is_input_mono: bool
    is_output_mono: bool
    native_sample_rates: List[int]
    native_buffer_sizes: List[int]
    sdk_version: str


class WaveformToWaveformBase(NeutoneModel):
    @abstractmethod
    def is_input_mono(self) -> bool:
        pass

    @abstractmethod
    def is_output_mono(self) -> bool:
        pass

    @abstractmethod
    def get_native_sample_rates(self) -> List[int]:
        """
        Returns a list of sample rates that the model was developed and tested
        with. If the list is empty, all common sample rates are assumed to be
        supported.
        Example value: [44100, 48000]
        """
        pass

    @abstractmethod
    def get_native_buffer_sizes(self) -> List[int]:
        """
        Returns a list of buffer sizes that the model was developed and tested
        with. If the list is empty, all common buffer sizes are assumed to be
        supported.
        Example value: [512, 1024, 2048]
        """
        pass

    @abstractmethod
    def do_forward_pass(
        self, x: Tensor, params: Optional[Dict[str, Tensor]] = None
    ) -> Tensor:
        """
        Perform a forward pass on a waveform-to-waveform model.
        TODO(christhetree)
        """
        pass

    def remap_params_for_forward_pass(self, params: Tensor) -> Dict[str, Tensor]:
        """
        params is expected to be a [n_params, buffer_size] Tensor sent by the plugin.

        By default we take the mean value of each parameter to provide a single value
        for the current buffer.

        For more fine grained control, override this method to receive the entire inputs.
        """
        assert params.shape[0] == len(self.get_parameters())
        return {
            param.name: value.mean()
            for param, value in zip(self.get_parameters(), params)
        }

    def forward(self, x: Tensor, params: Optional[Tensor] = None) -> Tensor:
        """
        Internal forward pass for a WaveformToWaveform model.

        If params is None, we fill in the default values.
        TODO(christhetree)
        """
        if params is None:
            # The default params come in as one value by default but for compatibility
            # with the plugin inputs we repeat them for the size of the buffer
            params = self.get_default_parameters().repeat(1, x.shape[1])
        validate_waveform(x)

        x = self.do_forward_pass(x, self.remap_params_for_forward_pass(params))

        validate_waveform(x)
        return x

    @tr.jit.export
    def calc_min_delay_samples(self) -> int:
        """
        If the model introduces a minimum amount of delay to the output audio,
        for example due to a lookahead buffer or cross-fading, return it here
        so that it can be forwarded to the DAW to compensate. Defaults to 0.

        This value may change if set_buffer_size() is used to change the buffer
        size, hence this is not a constant attribute.
        """
        return 0

    @tr.jit.export
    def set_buffer_size(self, n_samples: int) -> bool:
        """
        If the model supports dynamic buffer size resizing, add the
        functionality here.

        Args:
            n_samples: The number of samples to resize the buffer to.

        Returns:
            bool: True if successful, False if not supported or unsuccessful.
                  Defaults to False.
        """
        return False

    @tr.jit.export
    def flush(self) -> Optional[Tensor]:
        """
        If the model supports flushing (e.g. due to a delay from a lookahead
        buffer or cross-fading etc.) add the functionality here.

        Returns:
            Optional[Tensor]: None if not supported, otherwise a right side zero
                              padded tensor of length buffer_size with the
                              flushed samples at the beginning.
        """
        return None

    @tr.jit.export
    def reset(self) -> bool:
        """
        If the model supports resetting (e.g. wiping internal state), add the
        functionality here.

        Returns:
            bool: True if successful, False if not supported or unsuccessful.
                  Defaults to False.
        """
        return False

    def get_preserved_attributes(self) -> List[str]:
        preserved_attrs = super().get_preserved_attributes()
        preserved_attrs.extend(
            [
                self.get_native_sample_rates.__name__,
                self.get_native_buffer_sizes.__name__,
                self.calc_min_delay_samples.__name__,
                self.set_buffer_size.__name__,
                self.flush.__name__,
                self.reset.__name__,
                self.to_metadata.__name__,
            ]
        )
        return preserved_attrs

    @tr.jit.export
    def to_metadata(self) -> WaveformToWaveformMetadata:
        core_metadata = self.to_core_metadata()
        return WaveformToWaveformMetadata(
            model_name=core_metadata.model_name,
            model_authors=core_metadata.model_authors,
            model_short_description=core_metadata.model_short_description,
            model_long_description=core_metadata.model_long_description,
            neutone_parameters=core_metadata.neutone_parameters,
            wet_default_value=core_metadata.wet_default_value,
            dry_default_value=core_metadata.dry_default_value,
            output_gain_default_value=core_metadata.output_gain_default_value,
            technical_description=core_metadata.technical_description,
            technical_links=core_metadata.technical_links,
            tags=core_metadata.tags,
            model_version=core_metadata.model_version,
            sdk_version=core_metadata.sdk_version,
            citation=core_metadata.citation,
            is_experimental=core_metadata.is_experimental,
            is_input_mono=self.is_input_mono(),
            is_output_mono=self.is_output_mono(),
            native_buffer_sizes=self.get_native_buffer_sizes(),
            native_sample_rates=self.get_native_sample_rates(),
        )
